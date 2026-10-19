# Deployment (Azure for Students) and local operation

**Status: the Azure templates compile and lint (Bicep CLI 0.48.1) but have NOT been deployed.** No
Azure credentials or Azure CLI were available in the build environment. Docker was not available
either, so the image is built only in CI.

## Local, no cloud credentials

```bash
python -m venv .venv && . .venv/Scripts/activate        # Windows; use bin/activate elsewhere
pip install -r requirements-dev.txt
export QGW_MODE=demo                                     # PowerShell: $env:QGW_MODE="demo"
python -m src.data.synthetic && python -m src.features.build
python -m src.pipeline.train --quick --final
uvicorn api.main:app --port 8000                         # http://localhost:8000/docs
streamlit run dashboard/streamlit_app.py                 # http://localhost:8501
```

With Docker: `docker compose -f docker/compose.yaml up --build` (demo mode).

## Azure design and alternatives

| need | chosen | why | alternative considered |
|---|---|---|---|
| API, dashboard | Container Apps (Consumption, min replicas 0) | per-second billing, monthly free grant, HTTPS ingress, revisions for rollback | App Service B1 (~USD 13/month always on); AKS (too costly) |
| batch jobs | Container Apps Jobs (cron + manual) | same image, billed only while running | Azure Functions (cold-start and size limits for torch/LightGBM); Azure ML pipelines (compute cost) |
| image registry | ACR Basic **or** public GHCR (`useAcr=false`) | ACR is private but ~USD 5/month; GHCR public images are free | Docker Hub |
| shared storage | Azure Files share mounted at `/mnt/qgw` | no code change: data/, artifacts/, reports/ paths via env vars | Blob + fsspec (cheaper per GB, needs code changes) |
| secrets | Key Vault (RBAC) referenced by managed identity | no secrets in images, env files or workflows | Container Apps inline secrets |
| logs | Log Analytics, 30-day retention, 0.2 GB/day cap | structured JSON logs from the API | Application Insights (add if tracing is needed) |
| experiment tracking / registry | file-based registry + JSON reports on the share | zero cost; lineage and audit log in `registry.json` / `audit.jsonl` | Azure ML workspace with MLflow (free workspace, but compute and storage add cost) |
| cost control | Consumption budget, alerts at 50%/80% actual and 100% forecast | student credit stops services when exhausted | - |

## Cost model (estimate, USD per month; verify with the Azure pricing calculator for your region)

Assumes: API and dashboard idle most of the time (scale to zero), ~2,000 requests/day, weekly ingest
(10 min at 1 vCPU) and drift (2 min at 0.5 vCPU), monthly retrain (15 min at 2 vCPU).

| item | estimate |
|---|---|
| Container Apps apps + jobs | ~0 (inside the per-subscription monthly free grant of vCPU-seconds, GiB-seconds and requests) |
| ACR Basic (if `useAcr=true`) | ~5 |
| Azure Files, 10 GiB provisioned quota, LRS | ~0.6-1 |
| Log Analytics (<= 0.2 GB/day, often far less) | ~0-1 |
| Key Vault operations | < 0.1 |
| **total** | **~1-2 with GHCR, ~6-8 with ACR** |

Keeping the dashboard warm (min replicas 1) would add roughly USD 15-30/month at 0.5 vCPU / 1 GiB, so
it is left at 0 (first request after idle takes ~20-40 s to cold-start).

## One-time Azure setup

```bash
az login
az group create -n rg-qglacierwatch -l centralindia      # pick a region your student policy allows
# 1) base resources, no apps yet
az deployment group create -g rg-qglacierwatch -f infra/main.bicep -p infra/main.parameters.json \
   -p alertEmail=you@example.com useAcr=false deployApps=false
# 2) secrets (values never committed)
az keyvault secret set --vault-name <kv> -n qgw-api-key --value "$(openssl rand -hex 24)"
az keyvault secret set --vault-name <kv> -n ee-service-account-json --file ee-key.json
#    (grant yourself "Key Vault Secrets Officer" on the vault first; it uses RBAC)
# 3) seed the file share with data/raw (or run the ingest job), then build/push the image and
#    redeploy with deployApps=true imageTag=<sha>   -- the CD workflow automates 3)
az storage file upload-batch --account-name <st> -s data/raw -d qgw/data/raw
```

GitHub OIDC for CD: create an Entra app registration with a federated credential for
`repo:<owner>/qglacierwatch:environment:production`, assign it Contributor on the resource group
(and User Access Administrator if the template must create role assignments), then set repository
variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`,
`ALERT_EMAIL`. Earth Engine in containers needs a service account registered for the EE project.

## Operations

- Health: `GET /health` (also used by liveness/readiness probes). `status=degraded` lists problems (stale data, no approved model).
- Logs: `ContainerAppConsoleLogs_CL` in Log Analytics; API emits one JSON line per request.
- Run a job now: `az containerapp job start -g rg-qglacierwatch -n qgw-job-train`.
- **Model rollback**: `python -m src.registry.registry rollback --approver NAME --reason "..."` inside a job container (registry lives on the share).
- **Application rollback**: `az containerapp revision list -n qgw-api -g rg-qglacierwatch`, then `az containerapp ingress traffic set -n qgw-api -g rg-qglacierwatch --revision-weight <previous>=100`.
- Monitoring to add when deployed: availability test on `/health`, alert on 5xx rate, alert on `data_age_days > 10`.

## Public deployment security

- Set `QGW_API_KEY` (Key Vault secret `qgw-api-key`); every `/v1` data route then requires `X-API-Key`.
- The in-process rate limiter is per replica. For public exposure put Azure API Management (Consumption tier) or Front Door in front for global rate limits and keys per client.
- The dashboard has no authentication. Before sharing publicly, enable Container Apps built-in authentication (Entra ID) on `qgw-dashboard`.
- Containers run as a non-root user; images are scanned with Trivy in CI; dependencies audited with pip-audit.
