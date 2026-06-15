# GitHub Actions — API CI/CD

Deploys to **solidcare-api-dev** on push to `develop`.

## Secrets (`development` environment)

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | `01d3ae07-a3f7-471a-b2f5-924b5c21eb42` |
| `AZURE_TENANT_ID` | `2bef6495-fa90-4da0-a1ff-8bc75bcf730a` |
| `AZURE_SUBSCRIPTION_ID` | `8dfb8ce9-340f-4cfc-aa92-89d6d46d0924` |

## OIDC

App registration: **github-solidcare-api**  
Federated credential subject: `repo:erdavinder2307/solidcare-api-v2:environment:development`

Create a GitHub **environment** named `development` in the API repo before deploying.

## Deployment

Offline zip via `scripts/azure/build-deploy-package.sh` with `SCM_DO_BUILD_DURING_DEPLOYMENT=false`.

**Do not commit this file if it contains rotating tokens.** Client/tenant/subscription IDs are not secret; rotate SWA tokens separately in the web repo doc.
