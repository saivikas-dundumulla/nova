# Deploying Nova to Azure App Service (single App Service, both processes)

This runs the whole app in one Linux App Service:
- **Streamlit UI** — public, listens on port **8501** (Azure routes external 443 → 8501 via `WEBSITES_PORT`).
- **FastAPI backend** — internal only, on `127.0.0.1:8000`; the UI calls it over localhost.

Both are launched by [`startup.sh`](startup.sh).

## Prerequisites

- Azure CLI (`az login`) with rights to create/deploy an App Service.
- A resource group and a **Linux** App Service plan (B1 or higher; the free tier has no Always On).
- Python **3.12** runtime (App Service does not offer 3.13).

## 1. Create the App Service (once)

```bash
RG=nova-rg
PLAN=nova-plan
APP=nova-ombuds            # must be globally unique
LOCATION=westeurope

az group create -n $RG -l $LOCATION
az appservice plan create -g $RG -n $PLAN --sku B1 --is-linux
az webapp create -g $RG -p $PLAN -n $APP --runtime "PYTHON:3.12"
```

## 2. Configure settings (secrets + persistence + ports)

Secrets live here as **Application settings** (env vars) — never commit `.env`.

```bash
az webapp config appsettings set -g $RG -n $APP --settings \
  WEBSITES_PORT=8501 \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true \
  NOVA_API_BASE="http://127.0.0.1:8000" \
  CONVERSATIONS_DIR="/home/data/conversations" \
  AUDIT_LOG_PATH="/home/data/logs/audit.log" \
  SESSION_JWT_SECRET="<long-random-string>" \
  AUTH_USERS_JSON='{"enduser1":{"password_hash":"<bcrypt>","role":"enduser"},"ombuds1":{"password_hash":"<bcrypt>","role":"ombuds"}}' \
  AZURE_SEARCH_ENDPOINT="https://novasearch.search.windows.net" \
  AZURE_SEARCH_API_KEY="<key>" \
  AZURE_SEARCH_API_VERSION="2026-05-01-preview" \
  AZURE_SEARCH_KNOWLEDGE_BASE="nova-kb"
```

Key points:
- **`/home` is the only persistent path.** `CONVERSATIONS_DIR` and `AUDIT_LOG_PATH` must live under `/home/data`, or per-user history and audit logs are wiped on every restart/scale.
- Generate a bcrypt hash with `python -c "from passlib.hash import bcrypt; print(bcrypt.hash('pw'))"`.
- Generate the JWT secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Enable web sockets (Streamlit needs them) and set the startup command:

```bash
az webapp config set -g $RG -n $APP \
  --web-sockets-enabled true \
  --startup-file "bash startup.sh"
```

## 3. Deploy the code

From the repo root:

```bash
az webapp up -g $RG -n $APP --runtime "PYTHON:3.12"
# or, if the app already exists:
az webapp deploy -g $RG -n $APP --src-path . --type zip
```

Oryx installs from `requirements.txt` during deployment (that's why `SCM_DO_BUILD_DURING_DEPLOYMENT=true`).

Then browse to `https://$APP.azurewebsites.net` and log in.

## 4. Verify

```bash
# tail the logs
az webapp log tail -g $RG -n $APP
```

You should see uvicorn start on 127.0.0.1:8000, then Streamlit on 8501. The health check is proxied only through the UI; to hit the API directly for a smoke test, use SSH (App Service → SSH) and `curl localhost:8000/health`.

## Important constraints

- **Keep it to a single instance / single worker.** The conversation store is JSON files guarded by an in-process lock. Scaling out (multiple instances) or running multiple uvicorn workers would let concurrent writers clobber each other. If you need to scale, move the store to a shared backend (Azure Files mount, Cosmos DB, or Postgres) — the `app/memory/store.py` module is the single place to swap.
- **Always On** should be enabled (App Service → Configuration → General settings) so the container isn't unloaded between requests.
- CORS isn't needed: the UI calls the API server-side over localhost, not from the browser.

## CI/CD (GitHub Actions)

The workflow at [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) runs two jobs:

- **test** — on every push and PR to `master`: installs deps, runs `ruff` and `pytest`.
- **deploy** — only on push to `master`, only if **test** passed: deploys the repo to App Service. Oryx builds from `requirements.txt` server-side (keep `SCM_DO_BUILD_DURING_DEPLOYMENT=true`).

### One-time setup (publish-profile method — default)

1. Set the app name as a repo **variable** (Settings → Secrets and variables → Actions → Variables), or rely on the `nova-ombuds` default in the workflow:
   - `AZURE_WEBAPP_NAME = nova-ombuds`
2. Get the publish profile and store it as a repo **secret** `AZURE_WEBAPP_PUBLISH_PROFILE`:
   ```bash
   az webapp deployment list-publishing-profiles -g nova-rg -n nova-ombuds --xml
   ```
   Copy the full XML into the secret. (Publish-profile auth requires **SCM basic auth publishing** to be enabled on the app: App Service → Configuration → General settings → “SCM Basic Auth Publishing Credentials” = On.)

Push to `master` and the app deploys after tests pass.

### Alternative: OIDC (no long-lived secret — recommended if basic auth is disabled)

If your org disables basic-auth publishing, use federated credentials instead:

1. Create an Entra app registration + federated credential scoped to this repo/branch, and grant it the **Website Contributor** role on the App Service.
2. Add repo secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`.
3. Replace the deploy step with:
   ```yaml
       permissions:
         id-token: write
         contents: read
       steps:
         - uses: actions/checkout@v4
         - uses: azure/login@v2
           with:
             client-id: ${{ secrets.AZURE_CLIENT_ID }}
             tenant-id: ${{ secrets.AZURE_TENANT_ID }}
             subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
         - uses: azure/webapps-deploy@v3
           with:
             app-name: ${{ vars.AZURE_WEBAPP_NAME || 'nova-ombuds' }}
             package: .
   ```
   (Drop the `publish-profile` input — `azure/login` provides the credential.)

