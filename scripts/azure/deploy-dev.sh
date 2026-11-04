#!/usr/bin/env bash
# Solidcare V2 — minimum-cost Azure dev deployment
# Prerequisites: az login, openssl, psql, alembic
#
# Database: the Supabase project "solidcare-dev" (Mumbai, free plan) since 3 Nov 2026. The Azure PostgreSQL server
# solidcare-pg-dev was deleted, so this script no longer creates a database server. Supabase exposes the public
# schema through its Data API: keep RLS on every table and grant nothing to the anon/authenticated roles.
# Pass the Supabase session-pooler URL (password URL-encoded) in DATABASE_URL:
#   postgresql+asyncpg://postgres.<project-ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?ssl=require
#
# Explicit exclusions (confirmed):
#   - No Redis          → set REDIS_ENABLED=false
#   - No Key Vault      → secrets in App Service settings
#   - No Container Apps → App Service on ASP-solidev-8397
#
# Estimated cost: $0/month (Supabase free plan, App Service plan shared)

set -euo pipefail

SUB="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID — do not commit subscription IDs to the repo}"
DATABASE_URL="${DATABASE_URL:?Set DATABASE_URL to the Supabase pooler URL (see the header) — never commit it}"
# psql takes the plain libpq form of the same URL
PSQL_URL="$(sed -E 's#\+asyncpg##; s#\?.*$#?sslmode=require#' <<<"$DATABASE_URL")"
RG="solidev"
LOCATION_SWA="eastasia"
SWA_NAME="solidcare-web-dev"
API_NAME="solidcare-api-dev"
PLAN_NAME="ASP-solidev-8397"
STORAGE_ACCOUNT="solidevfunctionstorage"
BLOB_CONTAINER="solidcare-documents"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -z "${JWT_SECRET:-}" ]]; then
  JWT_SECRET="$(openssl rand -hex 64)"
  echo "Generated JWT_SECRET (save this)"
fi

echo "=== Step 1: Static Web App ==="
az staticwebapp show -n "$SWA_NAME" -g "$RG" --subscription "$SUB" -o none 2>/dev/null || \
az staticwebapp create \
  --name "$SWA_NAME" \
  --resource-group "$RG" \
  --location "$LOCATION_SWA" \
  --sku Free \
  --subscription "$SUB"

SWA_HOST="$(az staticwebapp show -n "$SWA_NAME" -g "$RG" --subscription "$SUB" --query defaultHostname -o tsv)"
echo "SWA hostname: https://$SWA_HOST"

echo "=== Step 2: Database (Supabase) ==="
psql "$PSQL_URL" -v ON_ERROR_STOP=1 -At -c "select 'database reachable: ' || current_database()"

echo "=== Step 3: (no database server to create) ==="

echo "=== Step 4: Blob container ==="
az storage container create \
  --account-name "$STORAGE_ACCOUNT" \
  --name "$BLOB_CONTAINER" \
  --auth-mode login \
  --public-access off \
  --subscription "$SUB" \
  -o none

STORAGE_CONN="$(az storage account show-connection-string -g "$RG" -n "$STORAGE_ACCOUNT" --subscription "$SUB" --query connectionString -o tsv)"

echo "=== Step 5: App Service ==="
az webapp show -n "$API_NAME" -g "$RG" --subscription "$SUB" -o none 2>/dev/null || \
az webapp create \
  --name "$API_NAME" \
  --resource-group "$RG" \
  --plan "$PLAN_NAME" \
  --runtime "PYTHON:3.11" \
  --subscription "$SUB"

CORS_ORIGINS='["https://'"${SWA_HOST}"'","https://solidcare.org","https://www.solidcare.org","http://localhost:5173"]'

echo "=== Step 6: App Settings ==="
az webapp config appsettings set \
  --name "$API_NAME" \
  --resource-group "$RG" \
  --subscription "$SUB" \
  --settings \
    ENV=development \
    REDIS_ENABLED=false \
    USE_KEY_VAULT=false \
    WEBSITES_PORT=8000 \
    AZURE_STORAGE_CONTAINER_NAME="$BLOB_CONTAINER" \
    DATABASE_URL="$DATABASE_URL" \
    DATABASE_POOL_SIZE=3 \
    DATABASE_MAX_OVERFLOW=3 \
    JWT_SECRET_KEY="$JWT_SECRET" \
    AZURE_STORAGE_CONNECTION_STRING="$STORAGE_CONN" \
    CORS_ORIGINS="$CORS_ORIGINS" \
  -o none

az webapp config set \
  --name "$API_NAME" \
  --resource-group "$RG" \
  --subscription "$SUB" \
  --startup-file "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1" \
  -o none

echo "=== Step 7: Migrations ==="
cd "$API_DIR"
DATABASE_URL="$DATABASE_URL" alembic upgrade head

echo "=== Step 8: Seed data ==="
psql "$PSQL_URL" -f scripts/seed_dev_admin.sql
psql "$PSQL_URL" -f scripts/seed_dev_rbac_users.sql

API_HOST="$(az webapp show -n "$API_NAME" -g "$RG" --subscription "$SUB" --query defaultHostName -o tsv)"

echo ""
echo "=== Deployment complete ==="
echo "Frontend:  https://$SWA_HOST"
echo "Backend:   https://$API_HOST"
echo "Health:    https://$API_HOST/health"
echo ""
echo "GitHub secrets to configure:"
echo "  VITE_API_BASE_URL=https://$API_HOST/api/v1"
echo "  AZURE_STATIC_WEB_APPS_TOKEN=<from: az staticwebapp secrets list -n $SWA_NAME -g $RG>"
echo ""
echo "Validate:"
echo "  curl https://$API_HOST/health"
echo "  Demo login: use seeded users from scripts/seed_dev_*.sql (rotate passwords on shared environments)"
