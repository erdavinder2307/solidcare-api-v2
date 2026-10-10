#!/bin/bash
# Database auto-stop: deploy and operate the function in this folder (see README.md).
#
# Usage: deploy.sh <command>
#   status   read-only: server state, function, role, metric setting, API settings (names only)
#   plan     read-only dry run: what `deploy` would create or change, and the role scope
#   deploy   create/update everything `plan` lists and publish the function code
#   wake     start the server through the function (same path the API uses)
#   stop     stop the server now
#   off      turn auto-stop off: disable the function, remove the API's wake settings, start the server
#
# Names come from the environment (no defaults, so nothing is deployed by accident):
#   RESOURCE_GROUP  SERVER_NAME  DATABASE_NAMES (comma separated: activity in any of them keeps the server up)
#   API_APP (App Service that gets DB_WAKE_URL/DB_WAKE_KEY)  FUNC_APP  STORAGE_ACCOUNT  LOCATION
# Needs an `az login` with rights to create these resources and assign a role on the server.
# Keys never appear in the output: they go from Azure straight into the app setting.
set -uo pipefail
CMD="${1:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
for v in RESOURCE_GROUP SERVER_NAME DATABASE_NAMES API_APP FUNC_APP STORAGE_ACCOUNT LOCATION; do
  [ -n "${!v:-}" ] || { echo "STOP: set $v (see the top of this script)"; exit 1; }
done
RG="$RESOURCE_GROUP"
ROLE_NAME="Database auto-stop ($SERVER_NAME)"
METRIC_PARAM="metrics.collector_database_activity"
say() { echo "- $*"; }

SUB=$(az account show --query id -o tsv) || { echo "STOP: az login needed"; exit 1; }
SERVER_ID=$(az postgres flexible-server show -g "$RG" -n "$SERVER_NAME" --query id -o tsv) \
  || { echo "STOP: server $SERVER_NAME not found in $RG"; exit 1; }

server_state() { az postgres flexible-server show --ids "$SERVER_ID" --query state -o tsv; }
func_exists() { az functionapp show -g "$RG" -n "$FUNC_APP" --query id -o tsv >/dev/null 2>&1; }
func_principal() { az functionapp identity show -g "$RG" -n "$FUNC_APP" --query principalId -o tsv 2>/dev/null; }
role_exists() { [ -n "$(az role definition list --name "$ROLE_NAME" --scope "$SERVER_ID" --query '[0].name' -o tsv 2>/dev/null)" ]; }
role_assigned() {
  local p; p=$(func_principal); [ -n "$p" ] || return 1
  [ -n "$(az role assignment list --assignee "$p" --scope "$SERVER_ID" --role "$ROLE_NAME" --query '[0].id' -o tsv 2>/dev/null)" ]
}
metric_param() {
  az postgres flexible-server parameter show -g "$RG" -s "$SERVER_NAME" -n "$METRIC_PARAM" --query value -o tsv 2>/dev/null
}
api_has_wake() {
  az webapp config appsettings list -g "$RG" -n "$API_APP" --query "[?name=='DB_WAKE_URL'].name" -o tsv | grep -q .
}
wake_key() { az functionapp keys list -g "$RG" -n "$FUNC_APP" --query functionKeys.default -o tsv; }
wake_url() { echo "https://$(az functionapp show -g "$RG" -n "$FUNC_APP" --query defaultHostName -o tsv)/api/wake"; }

status() {
  say "server $SERVER_NAME: $(server_state)"
  say "metric setting $METRIC_PARAM: $(metric_param || echo unknown)"
  if func_exists; then
    say "function app $FUNC_APP: $(az functionapp show -g "$RG" -n "$FUNC_APP" --query state -o tsv)"
    say "  identity: $([ -n "$(func_principal)" ] && echo system-assigned || echo NONE)"
    say "  role '$ROLE_NAME' on the server: $(role_assigned && echo assigned || echo NOT assigned)"
    say "  watched databases: $(az functionapp config appsettings list -g "$RG" -n "$FUNC_APP" --query "[?name=='DATABASE_NAMES'].value" -o tsv)"
  else
    say "function app $FUNC_APP: not created"
  fi
  say "API $API_APP wake settings: $(api_has_wake && echo set || echo not set)"
  say "API $API_APP health check path: $(az webapp config show -g "$RG" -n "$API_APP" --query healthCheckPath -o tsv)"
}

plan() {
  echo "Subscription $SUB · resource group $RG · location $LOCATION"
  az storage account show -g "$RG" -n "$STORAGE_ACCOUNT" >/dev/null 2>&1 \
    && say "storage $STORAGE_ACCOUNT: exists" || say "storage $STORAGE_ACCOUNT: WOULD CREATE (Standard_LRS, state + stop/start log tables)"
  func_exists && say "function app $FUNC_APP: exists, WOULD UPDATE code and settings" \
    || say "function app $FUNC_APP: WOULD CREATE (Linux consumption, Python 3.11, system-assigned identity)"
  role_exists && say "custom role '$ROLE_NAME': exists" \
    || say "custom role '$ROLE_NAME': WOULD CREATE, assignable only on the server"
  say "  actions: flexibleServers/read, flexibleServers/start/action, flexibleServers/stop/action, Insights metrics/read"
  role_assigned && say "role assignment: exists" || say "role assignment: WOULD ASSIGN to the function's identity, scope = the server only"
  [ "$(metric_param)" = "on" ] && say "$METRIC_PARAM: on" \
    || say "$METRIC_PARAM: WOULD SET on (dynamic, no restart; needed for the xact_total metric)"
  say "function settings: WOULD SET SUBSCRIPTION_ID, RESOURCE_GROUP, SERVER_NAME, DATABASE_NAMES=$DATABASE_NAMES"
  say "databases on the server: $(az postgres flexible-server db list -g "$RG" -s "$SERVER_NAME" --query "[].name" -o tsv | grep -vxE 'azure_maintenance|azure_sys|postgres' | tr '\n' ' ')(watched: $DATABASE_NAMES; any other one stops working while the server is stopped)"
  api_has_wake && say "API $API_APP: DB_WAKE_URL/DB_WAKE_KEY already set (WOULD REFRESH)" \
    || say "API $API_APP: WOULD SET DB_WAKE_URL and DB_WAKE_KEY (the key goes from Azure into the setting, never shown)"
  say "server $SERVER_NAME is $(server_state); deploy does not stop or start it"
  echo "DRY RUN: nothing changed."
}

deploy() {
  set -e
  az storage account show -g "$RG" -n "$STORAGE_ACCOUNT" >/dev/null 2>&1 \
    || az storage account create -g "$RG" -n "$STORAGE_ACCOUNT" -l "$LOCATION" --sku Standard_LRS --min-tls-version TLS1_2 -o none
  say "storage ready"
  func_exists || az functionapp create -g "$RG" -n "$FUNC_APP" --storage-account "$STORAGE_ACCOUNT" \
    --consumption-plan-location "$LOCATION" --os-type Linux --runtime python --runtime-version 3.11 \
    --functions-version 4 --assign-identity '[system]' -o none
  say "function app ready"
  if ! role_exists; then
    local def; def=$(mktemp)
    cat > "$def" <<EOF
{"Name": "$ROLE_NAME", "IsCustom": true,
 "Description": "Read metrics of one PostgreSQL flexible server and start or stop it (auto-stop when idle).",
 "Actions": ["Microsoft.DBforPostgreSQL/flexibleServers/read",
             "Microsoft.DBforPostgreSQL/flexibleServers/start/action",
             "Microsoft.DBforPostgreSQL/flexibleServers/stop/action",
             "Microsoft.Insights/metrics/read"],
 "AssignableScopes": ["$SERVER_ID"]}
EOF
    az role definition create --role-definition "$def" -o none
    rm -f "$def"
    sleep 30  # a new role definition takes a moment to be assignable
  fi
  role_assigned || az role assignment create --assignee-object-id "$(func_principal)" \
    --assignee-principal-type ServicePrincipal --role "$ROLE_NAME" --scope "$SERVER_ID" -o none
  say "role assigned (scope: the server only)"
  az postgres flexible-server parameter set -g "$RG" -s "$SERVER_NAME" -n "$METRIC_PARAM" --value on -o none
  say "$METRIC_PARAM on"
  az functionapp config appsettings set -g "$RG" -n "$FUNC_APP" -o none --settings \
    SUBSCRIPTION_ID="$SUB" RESOURCE_GROUP="$RG" SERVER_NAME="$SERVER_NAME" DATABASE_NAMES="$DATABASE_NAMES" \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true
  local zip; zip="$(mktemp -d)/db-autostop.zip"
  (cd "$HERE" && zip -qr "$zip" function_app.py autostop_core.py host.json requirements.txt)
  az functionapp deployment source config-zip -g "$RG" -n "$FUNC_APP" --src "$zip" --build-remote true -o none
  rm -f "$zip"
  say "function code published"
  az webapp config appsettings set -g "$RG" -n "$API_APP" -o none \
    --settings DB_WAKE_URL="$(wake_url)" DB_WAKE_KEY="$(wake_key)"
  say "API wake settings set (restarts the API)"
  echo "DEPLOYED. The first idle check runs within 10 minutes; the server stops after 30 idle minutes."
}

wake() {
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "x-functions-key: $(wake_key)" "$(wake_url)")
  say "wake: HTTP $code (200 ready, 202 starting); server now $(server_state)"
}

stop() {
  [ "$(server_state)" = "Ready" ] || { say "server is $(server_state); stop only works from Ready"; return 0; }
  az postgres flexible-server stop -g "$RG" -n "$SERVER_NAME" --no-wait -o none
  say "stop requested; server now $(server_state)"
}

off() {
  set -e
  func_exists && az functionapp stop -g "$RG" -n "$FUNC_APP" -o none && say "function app stopped (kept, not deleted)"
  az webapp config appsettings delete -g "$RG" -n "$API_APP" --setting-names DB_WAKE_URL DB_WAKE_KEY -o none
  say "API wake settings removed (restarts the API)"
  local state tries=0
  state=$(server_state)
  while [ "$state" = "Stopping" ] || [ "$state" = "Starting" ] || [ "$state" = "Updating" ]; do
    [ "$tries" -ge 20 ] && break
    say "server is $state; waiting 30 s for it to settle"
    sleep 30; tries=$((tries + 1)); state=$(server_state)
  done
  if [ "$state" = "Stopped" ]; then
    az postgres flexible-server start -g "$RG" -n "$SERVER_NAME" --no-wait -o none
  elif [ "$state" != "Ready" ]; then
    say "WARNING: server is still $state after 10 minutes, so it was not started. Run 'off' again shortly."
  fi
  say "server: $(server_state). Auto-stop is off; run deploy again to turn it back on."
}

case "$CMD" in
  status) status ;;
  plan) plan ;;
  deploy) deploy ;;
  wake) wake ;;
  stop) stop ;;
  off) off ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
