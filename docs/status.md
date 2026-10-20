# Milestone checklist and verification log

Environment: Windows 11, Python 3.12.6 venv (`.venv`, pins in `requirements*.txt`), 16 logical
CPUs, 24 GB RAM, no GPU, no Docker, Azure CLI 2.91.0 + Bicep 0.48.1 (no subscription yet), Earth
Engine credentials present (project `ee-senthil-hydro`), internet access. Last update 2026-10-20.

| milestone | state | verification |
|---|---|---|
| A. skeleton, configs, SYNTHETIC fixture, offline tests | done | `pytest` |
| B. validation, provenance, ingestion adapters | done | real ingest re-run (MODIS 3,997 d, ERA5 4,018 d, GloFAS 4,018 d); schemas pass; DVC remote pushed 2026-10-20 |
| C. baselines, LightGBM quantile, quantile LSTM | done | real CV + final fit |
| D. evaluation, CQR, seasonal metrics, block bootstrap | done; gate not passed | first run + one registered per-season CQR re-run (`docs/protocol.md`); 30-day coverage 0.689 < 0.70 |
| E. quantum benchmark | done | `reports/real/quantum_benchmark.md` (7 models x 5 seeds) |
| F. lake segmentation and areas | ran and evaluated | 20 m, water-stratified split; val IoU 0.37, test IoU 0.11 (over-maps water vs JRC); no growth flags after BH correction |
| G. season-aware drift, tiered retraining, registry | done | replay 522 checks; 72 synthetic events; Tier-3 run; registry tests; weekly `--latest` check now persisted |
| H. API and dashboard | done | API tests incl. auth/rate limit/validation; 7 pages render; snow-cover map added |
| I. Docker, Azure IaC, CI/CD | prepared, **not deployed** | CI green (tests, Trivy, Bicep); `scripts/azure/*` tested against a fake `az`; no Azure resources exist |
| J. end-to-end validation, docs | done | e2e test runs synthetic -> features -> train -> registry -> retrain -> API |

## Pending checklist

Research validation (do not let cloud work replace these):

- [ ] **Hi-MAG comparison**: locate Chen et al. (2021) inventory, verify source/licence/CRS/dates, clip to the basin, run `src.lakes.pipeline.compare_inventory`, report overlap and area differences, or document the exact blocker.
- [ ] **Fresh 2026 forecast evaluation**: commit a protocol first; verify Jan-Sep 2026 data exist (provenance, coverage, timestamps); train 2015-2023, calibrate 2024-2025, evaluate once on 2026; no tuning on 2026.
- [ ] **Lake-segmentation improvement**: SWIR (MNDWI), terrain-shadow and slope filters, S1 features, selected on validation only, frozen before one test evaluation; disclose that the JRC reference ends in 2021 and the test split was seen before.

Cloud (blocked on the student subscription):

- [x] Pre-flight, deploy, verify and cleanup scripts; GHCR image workflow; env template; metric alerts; cost documentation (`docs/deployment.md`).
- [ ] Student subscription active (user: check the Azure portal, then `az login`).
- [ ] `preflight.ps1` passes on the real subscription.
- [ ] GHCR package published by the `image` workflow and made public.
- [ ] User approves the resource plan, then `deploy.ps1`.
- [ ] `verify.ps1 -WriteTest` passes (endpoints, auth, inference, share write, alerts).

External:

- [ ] Observed CWC Bhuntar discharge: formal data request (see `docs/gauge_data_request.md`); until then GloFAS v4 is the target.

## Blockers and external dependencies

- Observed discharge (CWC Bhuntar) not publicly available; GloFAS used. Supply `data/raw/discharge_gauge.csv` to switch.
- Azure: student subscription verification pending; then `az login` and the steps in `docs/deployment.md`.
- Docker: needed to build/run the image locally (CI builds it).
- Earth Engine service account: needed for scheduled ingestion in Azure (`deploy.ps1 -EeKeyFile`).
- Hi-MAG/ICIMOD lake inventories: download and licence check pending.
