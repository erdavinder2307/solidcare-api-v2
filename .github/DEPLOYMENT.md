# GitHub Actions — API CI/CD

Deploys to **solidcare-api-dev** on push to `main` or `develop`.

## Secrets (`development` environment)

| Secret | How to obtain |
|---|---|
| `AZURE_CLIENT_ID` | App registration **github-solidcare-api** |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_STORAGE_CONNECTION_STRING` | `az storage account show-connection-string -g solidev -n solidevfunctionstorage -o tsv` |

## OIDC

App registration: **github-solidcare-api**  
Federated credential subject: `repo:erdavinder2307/solidcare-api-v2:environment:development`

Create a GitHub **environment** named `development` in the API repo before deploying.

## Deployment method

CI builds a slim offline zip (`requirements-deploy.txt`, ~37MB) and deploys via **run-from-package**:

1. Upload zip to blob `solidcare-deployments/api/latest.zip`
2. Set `WEBSITE_RUN_FROM_PACKAGE` to a read SAS URL
3. Restart the App Service

This avoids Kudu zip extraction, which returns **502** on the F1 plan for large packages.

Local/manual deploy:

```bash
bash scripts/azure/build-deploy-package.sh /tmp/api-package
(cd /tmp/api-package && zip -r ../solidcare-api.zip .)
AZURE_STORAGE_CONNECTION_STRING='...' \
AZURE_RESOURCE_GROUP=solidev \
AZURE_WEBAPP_NAME=solidcare-api-dev \
bash scripts/azure/deploy-run-from-package.sh /tmp/solidcare-api.zip
```
