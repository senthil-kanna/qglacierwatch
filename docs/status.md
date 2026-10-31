# Milestone checklist and verification log

Environment: Windows 11, Python 3.12.6 venv (`.venv`, pins in `requirements*.txt`), 16 logical
CPUs, 24 GB RAM, no GPU, no Docker, Azure CLI 2.91.0 + Bicep 0.48.1 (no subscription yet), Earth
Engine credentials present (project `ee-senthil-hydro`), internet access. Last update 2026-10-20.

| milestone | state | verification |
|---|---|---|
| A. skeleton, configs, SYNTHETIC fixture, offline tests | done | `pytest` |
| B. validation, provenance, ingestion adapters | done | real ingest re-run (MODIS 3,997 d, ERA5 4,018 d, GloFAS 4,018 d); schemas pass; DVC remote pushed 2026-10-20 |
| C. baselines, LightGBM quantile, quantile LSTM | done | real CV + final fit |
| D. evaluation, CQR, seasonal metrics, block bootstrap | done; gate not passed | 2023-25: first run + registered per-season CQR re-run, 30-day coverage 0.689 < 0.70. Fresh 2026 test (registered): over-coverage 0.938 / 0.955 > 0.90 |
| E. quantum benchmark | done | `reports/real/quantum_benchmark.md` (7 models x 5 seeds) |
| F. lake segmentation and areas | ran and evaluated | 20 m, water-stratified split; val IoU 0.37, test IoU 0.11 (over-maps water vs JRC); no growth flags after BH correction |
| G. season-aware drift, tiered retraining, registry | done | replay 522 checks; 72 synthetic events; Tier-3 run; registry tests; weekly `--latest` check now persisted |
| H. API and dashboard | done | API tests incl. auth/rate limit/validation; 7 pages render; snow-cover map added |
| I. Docker, cloud IaC, CI/CD | AWS prepared (branch `feat/aws-deployment`), **not applied**; Azure kept as alternative | Terraform validate + cost guards, slim API image served from a clean venv, `scripts/aws/*` and `scripts/azure/*` tested against fake CLIs; no cloud resources exist |
| J. end-to-end validation, docs | done | e2e test runs synthetic -> features -> train -> registry -> retrain -> API |

## Pending checklist

Research validation (do not let cloud work replace these):

- [x] **Hi-MAG comparison** (2026-10-20): v3.0, CC BY 4.0, MD5 verified; method committed before scoring (aa18713); 17/21 Hi-MAG 2017 lakes >= 0.01 km2 found (88% of area), matched areas ~0.5x Hi-MAG, 11 extra objects; no common year (Hi-MAG ends 2017). `reports/real/himag_comparison.md`.
- [x] **Fresh 2026 forecast evaluation** (2026-10-20): protocol 2a9c688 before data; test scored once. gbm NSE 0.994/0.980/0.962; gate failed on over-coverage (0.938 at 1 d, 0.955 at 30 d); VQC worse than all classical models. Found and corrected the target provenance (forecast-derived after 2023-08-04). 2026 consumed. `docs/protocol_fresh2026.md`.
- [x] **Lake-segmentation improvement** (2026-10-20, registered e1dbdd2): 6 variants (MNDWI, slope 20 deg, SWIR guard, SAR union) selected on validation; none beat the current rule (val IoU 0.156 vs <= 0.094), so the rule is unchanged; test 2021 once, IoU 0.077 in the wider domain. JRC ends 2021; test not untouched. Negative result documented.

Cloud, AWS (primary since 2026-10-24; target: working 2026-10-30, stable 2026-11-07; `docs/aws-deployment.md`):

- [x] Terraform `infra/aws`, S3 storage layer, Lambda job handler, slim API image, CI deploy job, scripts, guide.
- [x] 2026-10-24 `aws login --profile qgw` works (account 078901481128, Free plan, USD 120 credit). Project SCP forces ap-southeast-2 and denies GitHub OIDC: moved to ap-southeast-2, CI uses a scoped IAM user (`github-keys.ps1`).
- [ ] `bootstrap.ps1 -CheckOnly`, then `bootstrap.ps1`; install `gh` (`winget install -e --id GitHub.cli`).
- [ ] `seed-data.ps1`; `github-keys.ps1`; push branch; CI `aws-deploy` pushes images.
- [ ] `deploy.ps1 -ImageTag <sha>`; verify checklist (section 6 of the guide).
- [ ] From 2026-11-05 dashboard kept running (stable IP); demo-day checklist; `github-keys.ps1 -Revoke` and destroy after mid-November.

Cloud, Azure (alternative; abandoned 2026-10-24, subscription never approved):

- [x] Pre-flight, deploy, verify and cleanup scripts; GHCR image workflow; env template; metric alerts; cost documentation (`docs/deployment.md`).
- [ ] Student subscription active (user: check the Azure portal, then `az login`).
- [ ] `preflight.ps1` passes on the real subscription.
- [ ] GHCR package published by the `image` workflow and made public.
- [ ] User approves the resource plan, then `deploy.ps1`.
- [ ] `verify.ps1 -WriteTest` passes (endpoints, auth, inference, share write, alerts).

External:

- [x] Gauge consistency check (2026-10-20, registered c5b244c): Bajoura Bridge (HP Water Dept via NWDP), 737 valid days 2023-07..2026-09; GloFAS NSE 0.21 vs gauge; forecasts NSE 0.1-0.3 vs gauge. Raw data private (terms unclear).
- [ ] Observed CWC Bhuntar discharge (long, quality-controlled record): formal data request (`docs/gauge_data_request.md`); until then GloFAS v4 is the target.
- [ ] Confirm NWDP redistribution terms (helpdesk-nwic@gov.in) before sharing any gauge series.

## Blockers and external dependencies

- Observed discharge (CWC Bhuntar) not publicly available; GloFAS used. Supply `data/raw/discharge_gauge.csv` to switch.
- AWS: user credentials and the steps in `docs/aws-deployment.md` (nothing is created without the user's go-ahead).
- Docker: needed to build/run the image locally (CI builds it).
- Earth Engine service account: optional; until it is stored in SSM `/qgw/ee-service-account-json` the weekly AWS refresh runs `--skip-ingest`.
- Lake reference data after 2017/2021: Hi-MAG ends 2017 and JRC GSW 1.4 ends 2021; no post-2021 reference exists in this project.
