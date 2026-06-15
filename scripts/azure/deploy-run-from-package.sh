#!/usr/bin/env bash
# Upload an offline API zip to Blob Storage and point App Service at it (run-from-package).
# Avoids Kudu zip extraction OOM on F1. Requires AZURE_STORAGE_CONNECTION_STRING.
#
# Usage:
#   AZURE_STORAGE_CONNECTION_STRING=... \
#   AZURE_RESOURCE_GROUP=solidev \
#   AZURE_WEBAPP_NAME=solidcare-api-dev \
#   bash scripts/azure/deploy-run-from-package.sh path/to/solidcare-api.zip

set -euo pipefail

ZIP_PATH="${1:?Usage: deploy-run-from-package.sh <zip-path>}"
RG="${AZURE_RESOURCE_GROUP:?Set AZURE_RESOURCE_GROUP}"
APP="${AZURE_WEBAPP_NAME:?Set AZURE_WEBAPP_NAME}"
CONN="${AZURE_STORAGE_CONNECTION_STRING:?Set AZURE_STORAGE_CONNECTION_STRING}"
CONTAINER="${AZURE_DEPLOY_CONTAINER:-solidcare-deployments}"
BLOB_NAME="${AZURE_DEPLOY_BLOB:-api/latest.zip}"

if [[ ! -f "$ZIP_PATH" ]]; then
  echo "Zip not found: $ZIP_PATH" >&2
  exit 1
fi

echo "Deploy zip size: $(ls -lh "$ZIP_PATH" | awk '{print $5}')"

ACCOUNT_NAME="$(echo "$CONN" | sed -n 's/.*AccountName=\([^;]*\).*/\1/p')"
if [[ -z "$ACCOUNT_NAME" ]]; then
  echo "Could not parse AccountName from AZURE_STORAGE_CONNECTION_STRING" >&2
  exit 1
fi

az storage container create \
  --connection-string "$CONN" \
  --name "$CONTAINER" \
  --only-show-errors \
  -o none 2>/dev/null || true

echo "Uploading to blob: $CONTAINER/$BLOB_NAME"
az storage blob upload \
  --connection-string "$CONN" \
  --container-name "$CONTAINER" \
  --name "$BLOB_NAME" \
  --file "$ZIP_PATH" \
  --overwrite \
  -o none

EXPIRY="$(date -u -d '+1 year' '+%Y-%m-%dT%H:%MZ' 2>/dev/null || date -u -v+1y '+%Y-%m-%dT%H:%MZ')"
SAS="$(az storage blob generate-sas \
  --connection-string "$CONN" \
  --container-name "$CONTAINER" \
  --name "$BLOB_NAME" \
  --permissions r \
  --expiry "$EXPIRY" \
  -o tsv)"

PKG_URL="https://${ACCOUNT_NAME}.blob.core.windows.net/${CONTAINER}/${BLOB_NAME}?${SAS}"

echo "Configuring run-from-package on $APP"
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings \
    WEBSITE_RUN_FROM_PACKAGE="$PKG_URL" \
    SCM_DO_BUILD_DURING_DEPLOYMENT=false \
    ENABLE_ORYX_BUILD=false \
    WEBSITES_CONTAINER_START_TIME_LIMIT=1800 \
    PYTHONPATH="/home/site/wwwroot:/home/site/wwwroot/.python_packages/lib/site-packages" \
  -o none

az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --startup-file "startup.sh" \
  -o none

echo "Restarting $APP"
az webapp restart --resource-group "$RG" --name "$APP" -o none

echo "Run-from-package deploy complete"
