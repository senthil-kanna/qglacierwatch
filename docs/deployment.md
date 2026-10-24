# Deployment (Azure for Students) and local operation

> **Alternative target.** The primary deployment is AWS: see [aws-deployment.md](aws-deployment.md).
> This page and `infra/azure/` are kept unchanged as the Azure Container Apps option.

## Status (2026-10-20)

| component | state |
|---|---|
| Container image | built and scanned in CI (`ci` workflow, green); published to GHCR by the `image` workflow (not yet run on `main`) |
| Infrastructure as code | `infra/azure/main.bicep` compiles with Bicep CLI 0.48.1, no warnings |
| Deployment scripts | `scripts/azure/{preflight,deploy,verify,cleanup}.ps1`; safety logic tested against a fake `az` (`tests/test_azure_scripts.py`) |
| Azure subscription | **not yet available** (student verification pending) |
| Azure resources, URLs, alerts | **not created, not verified** |

Nothing in this file claims a working cloud deployment. `verify.ps1` prints PASS only for checks
that succeeded against real Azure resources.

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

With Docker: `docker compose -f docker/compose.yaml up --build` (demo mode). Training, satellite
processing and quantum simulations stay local; the cloud only serves the API and dashboard and
runs small scheduled jobs.

## Architecture

| need | chosen | why | alternative considered |
|---|---|---|---|
| API, dashboard | Container Apps, Consumption plan, min replicas 0 | per-second billing, monthly free grant, HTTPS ingress, revisions for rollback | App Service B1 (always on); AKS (cost) |
| batch jobs | Container Apps Jobs (weekly ingest + drift; manual train + lakes) | same image, billed only while running | Azure ML pipelines (compute cost) |
| image registry | **GHCR, public package** (`useAcr=false`) | free; repository is public | ACR Basic (USD ~5/month, private) |
| shared storage | **Azure Files** share mounted at `/mnt/qgw` | apps read/write it as a folder: no code change | Blob Storage (Container Apps cannot mount Blob; every read/write would need code changes) |
| secrets | Key Vault (RBAC) via user-assigned managed identity | no secrets in images, env files or workflows | inline Container Apps secrets |
| logs | Log Analytics, 30-day retention, 0.2 GB/day cap | structured JSON API logs | Application Insights SDK (not needed yet) |
| alerts | 2 metric alerts (API 5xx, restarts) + e-mail action group | do not wake a scaled-to-zero app | synthetic availability ping (see Monitoring) |
| cost control | resource-group budget, e-mail at 50% / 80% actual, 100% forecast | early warning | - |

Every resource carries the tag `project=qglacierwatch`; `cleanup.ps1` refuses to delete anything
without it.

### Verified platform behaviour (Microsoft Learn, read 2026-10-20)

- **Azure Files mount**: files written under the mount persist in the share and are visible to
  other replicas, revisions and apps; Container Apps supports SMB without a custom VNet and accepts
  `mountOptions` ([storage mounts](https://learn.microsoft.com/azure/container-apps/storage-mounts)).
  SMB has no POSIX owners, so the template mounts with `uid=10001,gid=10001` (the image's non-root
  user) and `nobrl` (no byte-range locks; the registry writes temp-file + rename). Container Apps
  cannot mount Blob Storage.
- **Write test after deployment**: `verify.ps1 -WriteTest` starts the drift job and checks that it
  wrote `reports/real/drift_latest.json` to the share. Until that passes, mount write permissions
  are unverified on real Azure.
- **Scale to zero**: no usage charges while scaled to zero; the last replica is removed 300 s after
  the last request (cool-down), so every visit costs at least ~5 min of replica time
  ([scaling](https://learn.microsoft.com/azure/container-apps/scale-app)).
- **No environment fee** for a Consumption-only environment. The Dedicated plan management charge
  applies to Dedicated workload profiles, private endpoints and planned maintenance, none of which
  the template uses ([billing](https://learn.microsoft.com/azure/container-apps/billing)).

## Cost estimate (estimates, not guarantees)

Prices: Azure Retail Prices API, region `centralindia`, retrieved 2026-10-20, USD. Free allowances:
[Azure for Students page](https://azure.microsoft.com/free/students/), read 2026-10-20. Prices and
offer terms change; re-check both before deploying and watch Cost Management after day 1.

**Azure for Students (as published):** USD 100 credit for 12 months, no credit card; Container Apps
always-free grant of 180,000 vCPU-s, 360,000 GiB-s and 2 million requests per month; services are
disabled (not billed to a card) when the credit runs out unless you upgrade.

| item | unit price | assumed use | estimate / month |
|---|---|---|---|
| Container Apps vCPU (active) | $0.000024 per vCPU-s ($0.086/h) | free grant covers ~100 replica-hours at 0.5 vCPU | $0 inside grant |
| Container Apps memory | $0.000003 per GiB-s | free grant covers ~100 replica-hours at 1 GiB | $0 inside grant |
| Requests | $0.40 per million | well under 2 M free | $0 |
| Jobs (ingest weekly 10 min @1 vCPU/2 GiB; drift weekly ~2 min @0.5/1; train 15 min @2/4 per run; lakes ~40 min @0.5/1 per run) | same meters | ~5,900 vCPU-s, ~11,700 GiB-s (~3% of grant) | $0 (≤ $0.15 if the grant were used up) |
| Azure Files, transaction optimized LRS | $0.066/GB stored; $0.015 per 10k writes | ~0.1 GB, few thousand writes | < $0.02 |
| Key Vault | $0.03 per 10k operations | a few hundred reads | < $0.01 |
| Log Analytics ingestion | first 5 GB/month free per billing account, then $3.22/GB | capped at 0.2 GB/day (≤ 6 GB) | $0 typical, ≤ $3.22 worst case |
| Metric alerts | ~$0.10 per monitored time series (retail API lists $0.00-0.10) | 2 rules | ≤ $0.20 |
| Action group e-mail | $0 | - | $0 |
| GHCR public image | free | - | $0 |
| Managed identity, budget, outbound data (≤ 100 GB) | free | - | $0 |
| **total** | | | **~$0-1 / month** |

What could spend the credit, and the guard against it:

| risk | cost | guard |
|---|---|---|
| min replicas ≥ 1 on an app | ~$39/month per app (0.5 vCPU, 1 GiB, always on) | template sets `minReplicas: 0`; do not change |
| Dedicated profile, private endpoint or planned maintenance | $0.10-0.14/hour (~$100/month) | none used |
| heavy traffic (bots) on public URLs | ~$0.054 per extra replica-hour | API key on `/v1`, rate limit, maxReplicas 2 (API) / 1 (dashboard) |
| log flood | $3.22/GB over 5 GB | 0.2 GB/day cap |
| switching to ACR | Basic $0.1666/day (~$5/month); Standard $0.6666/day (~$20/month after any free period) | GHCR |
| forgetting resources after the project | small, but credit ticks down | `cleanup.ps1` |

### Monitoring decision

- **Chosen**: metric alerts on the API (`Requests` with `statusCodeCategory=5xx` > 5 in 15 min;
  `RestartCount` > 2 in 15 min), evaluated every 5 min on platform metrics, e-mailed through an
  action group. These do not send traffic, so the app still scales to zero. Limitation: they detect
  errors and crash loops while the app is used; they cannot detect "down while nobody visits".
- **Rejected for the student budget**: a synthetic availability ping (Application Insights standard
  test, $0.0007 per execution). Every 15 min from one location costs ~$2/month for the test itself,
  but each ping keeps a replica alive for the 300 s cool-down: ~8-9 h/day awake, ~270 h/month at
  0.5 vCPU / 1 GiB, which exceeds the free grant by ~$9. Total ~$11/month. Use `verify.ps1` on
  demand instead; add the ping later only with `minReplicas` and budget reconsidered.
- After deployment, Azure sends a confirmation e-mail for the action group; alerts are not
  verified until a rule shows as enabled in `verify.ps1` and you have received that e-mail.

### Registry visibility

The `image` workflow pushes `ghcr.io/senthil-kanna/qglacierwatch:<git-sha>`. GHCR creates new
packages as **private**; Container Apps pulls anonymously, so make the package public once:
GitHub > your profile > Packages > qglacierwatch > Package settings > Change visibility > Public.
`preflight.ps1 -ImageTag <sha>` checks anonymous pull and fails otherwise.

## Steps once the student subscription is approved

All commands from the repository root in PowerShell. Scripts never deploy without you typing the
resource-group name, and `preflight.ps1` creates nothing.

```powershell
# 0. Log in and select the student subscription
az login
az account list -o table
az account set -s "<subscription id>"

# 1. Publish the image: GitHub > Actions > image > Run workflow (or merge to main).
#    Then make the GHCR package public (see Registry visibility) and note the commit SHA.

# 2. Read-only checks (add -RegisterProviders if it reports unregistered providers)
./scripts/azure/preflight.ps1 -Location centralindia -ImageTag <git-sha>

# 3. Deploy (what-if preview, typed confirmation, secrets, data upload, apps, verification)
./scripts/azure/deploy.ps1 -AlertEmail you@example.com -ImageTag <git-sha>
#    optional: -EeKeyFile path\to\ee-service-account.json  (enables the ingest/lakes jobs)
#    optional: -BaseOnly to create only the base resources first

# 4. Verify again later, including a write through the Azure Files mount
./scripts/azure/verify.ps1 -WriteTest
```

If `preflight.ps1` reports that `centralindia` is not allowed, re-run with one of the regions it
lists (`-Location <region>`) and pass the same `-Location` to `deploy.ps1`.

### GitHub OIDC for the `cd` workflow (optional, after the first manual deploy)

Create an Entra app registration with a federated credential for
`repo:senthil-kanna/qglacierwatch:environment:production`, assign it Contributor and User Access
Administrator on the resource group, then set repository variables `AZURE_CLIENT_ID`,
`AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `ALERT_EMAIL`. Earth Engine in
containers needs a service account registered for the EE project.

## Cleanup

```powershell
./scripts/azure/cleanup.ps1 -DryRun                      # shows subscription, group, resources
./scripts/azure/cleanup.ps1 -SubscriptionId <id>         # asks you to type the group name
./scripts/azure/cleanup.ps1 -SubscriptionId <id> -PurgeKeyVault   # also purge the soft-deleted vault
```

It deletes only the `rg-qglacierwatch` group, and aborts if the group or any resource in it lacks
the `project=qglacierwatch` tag. It does not touch Entra app registrations (delete those by hand)
or the GHCR package. Check Cost Management 1-2 days later for trailing charges.

## Operations

- Health: `GET /health` (also liveness/readiness probes). `status=degraded` lists problems (stale data, no approved model).
- Logs: `ContainerAppConsoleLogs_CL` in Log Analytics; the API emits one JSON line per request.
- Weekly drift check result: `reports/real/drift_latest.json` on the share.
- Run a job now: `az containerapp job start -g rg-qglacierwatch -n qgw-job-train`.
- **Model rollback**: `python -m src.registry.registry rollback --approver NAME --reason "..."` inside a job container (registry lives on the share).
- **Application rollback**: `az containerapp revision list -n qgw-api -g rg-qglacierwatch`, then `az containerapp ingress traffic set -n qgw-api -g rg-qglacierwatch --revision-weight <previous>=100`.

## Public deployment security

- `deploy.ps1` stores a random `qgw-api-key` in Key Vault; every `/v1` data route then requires `X-API-Key`. `/health` stays public.
- The in-process rate limiter is per replica. For wider exposure put API Management (Consumption) or Front Door in front.
- The dashboard has no authentication. Before sharing publicly, enable Container Apps built-in authentication (Entra ID) on `qgw-dashboard`.
- Containers run as a non-root user (uid 10001); images are scanned with Trivy in CI; dependencies audited with pip-audit.
