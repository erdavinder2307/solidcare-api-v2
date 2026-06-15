#!/usr/bin/env bash
# Solidcare V2 — minimum-cost Azure dev deployment
# Prerequisites: az login, openssl, psql, alembic
#
# Explicit exclusions (confirmed):
#   - No Redis          → set REDIS_ENABLED=false
#   - No Key Vault      → secrets in App Service settings
#   - No Container Apps → App Service on ASP-solidev-8397
#
# Estimated cost: ~$13-14/month (PostgreSQL B1ms only)

set -euo pipefail

SUB="${AZURE_SUBSCRIPTION_ID:?Set AZURE_SUBSCRIPTION_ID — do not commit subscription IDs to the repo}"
RG="solidev"
LOCATION_PG="centralindia"
LOCATION_SWA="eastasia"
SWA_NAME="solidcare-web-dev"
API_NAME="solidcare-api-dev"
PLAN_NAME="ASP-solidev-8397"
PG_NAME="solidcare-pg-dev"
PG_DB="solidcare_dev"
PG_USER="solidcare_admin"
STORAGE_ACCOUNT="solidevfunctionstorage"
BLOB_CONTAINER="solidcare-documents"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -z "${PG_PASS:-}" ]]; then
  PG_PASS="$(openssl rand -base64 24)"
  echo "Generated PG_PASS (save this): $PG_PASS"
fi

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

echo "=== Step 2: PostgreSQL Flexible Server ==="
az postgres flexible-server show -n "$PG_NAME" -g "$RG" --subscription "$SUB" -o none 2>/dev/null || \
az postgres flexible-server create \
  --name "$PG_NAME" \
  --resource-group "$RG" \
  --location "$LOCATION_PG" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --admin-user "$PG_USER" \
  --admin-password "$PG_PASS" \
  --public-access 0.0.0.0 \
  --subscription "$SUB"

PG_FQDN="$(az postgres flexible-server show -n "$PG_NAME" -g "$RG" --subscription "$SUB" --query fullyQualifiedDomainName -o tsv)"

echo "=== Step 3: Database ==="
az postgres flexible-server db show -g "$RG" --server-name "$PG_NAME" --database-name "$PG_DB" --subscription "$SUB" -o none 2>/dev/null || \
az postgres flexible-server db create \
  --resource-group "$RG" \
  --server-name "$PG_NAME" \
  --database-name "$PG_DB" \
  --subscription "$SUB"

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

DATABASE_URL="postgresql+asyncpg://${PG_USER}:${PG_PASS}@${PG_FQDN}:5432/${PG_DB}?ssl=require"

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
psql "postgresql://${PG_USER}:${PG_PASS}@${PG_FQDN}:5432/${PG_DB}?sslmode=require" -f scripts/seed_dev_admin.sql
psql "postgresql://${PG_USER}:${PG_PASS}@${PG_FQDN}:5432/${PG_DB}?sslmode=require" -f scripts/seed_dev_rbac_users.sql

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
