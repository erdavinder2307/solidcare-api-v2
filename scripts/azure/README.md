# Solidcare V2 — Azure Dev Deployment

Minimum-cost demo/dev architecture (~**$13–14/month**).

## Explicit exclusions (confirmed)

| Service | Status |
|---|---|
| Redis | **Not provisioned** — `REDIS_ENABLED=false` |
| Key Vault | **Not provisioned** — secrets in App Service settings |
| Container Apps | **Not used** — App Service on `ASP-solidev-8397` |

## Architecture

```
React (SWA Free) → FastAPI (App Service F1) → PostgreSQL B1ms
                              ↓
                    solidevfunctionstorage/solidcare-documents
```

## One-command deploy

```bash
# Requires: az login, psql, alembic (from solidcare-api-v2 venv)
export PG_PASS="$(openssl rand -base64 24)"   # save this
export JWT_SECRET="$(openssl rand -hex 64)"   # save this

bash solidcare-api-v2/scripts/azure/deploy-dev.sh
```

## App Service settings (reference)

| Setting | Value |
|---|---|
| `ENV` | `development` |
| `REDIS_ENABLED` | `false` |
| `USE_KEY_VAULT` | `false` |
| `DATABASE_URL` | `postgresql+asyncpg://...@solidcare-pg-dev...?ssl=require` |
| `JWT_SECRET_KEY` | strong random hex |
| `AZURE_STORAGE_CONNECTION_STRING` | from storage account |
| `AZURE_STORAGE_CONTAINER_NAME` | `solidcare-documents` |
| `CORS_ORIGINS` | `["https://<swa-hostname>","https://solidcare.org","https://www.solidcare.org","http://localhost:5173"]` |

## GitHub secrets (CI/CD)

See [`.github/DEPLOYMENT.md`](../.github/DEPLOYMENT.md) for full setup.

| Secret | Purpose |
|---|---|
| `VITE_API_BASE_URL` | `https://solidcare-api-dev.azurewebsites.net/api/v1` |
| `AZURE_STATIC_WEB_APPS_TOKEN` | SWA deployment token |
| `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` | OIDC for API zip deploy to App Service |

## Demo limitations (no Redis)

- Login and JWT access tokens work
- Refresh tokens work (no server-side revocation)
- Logout clears client tokens only
- Password reset disabled
- Rate limiting disabled

## Validate

```bash
curl https://solidcare-api-dev.azurewebsites.net/health
# Login: use seeded demo users (see scripts/seed_dev_admin.sql)
```
