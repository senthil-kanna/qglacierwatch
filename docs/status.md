# Milestone checklist and verification log

Environment: Windows 11, Python 3.12.6 venv (`.venv`, pins in `requirements*.txt`), 16 logical
CPUs, 24 GB RAM, no GPU, no Docker, no Azure CLI, Earth Engine credentials present
(project `ee-senthil-hydro`), internet access. Work date 2026-10-19.

| milestone | state | verification |
|---|---|---|
| A. skeleton, configs, SYNTHETIC fixture, offline tests | done | `pytest` |
| B. validation, provenance, ingestion adapters | done | real ingest re-run (MODIS 3,997 d, ERA5 4,018 d, GloFAS 4,018 d); schemas pass |
| C. baselines, LightGBM quantile, quantile LSTM | done | real CV + final fit |
| D. evaluation, CQR, seasonal metrics, block bootstrap | done | `reports/real/forecast_results.md`; test scored once (`artifacts/real/test_access.log`) |
| E. quantum benchmark | done | `reports/real/quantum_benchmark.md` (7 models x 5 seeds) |
| F. lake segmentation and areas | ran and evaluated | Earth Engine run at 20 m, water-stratified split; val IoU 0.37, test IoU 0.11 (over-maps water vs JRC); no growth flags after BH correction |
| G. season-aware drift, tiered retraining, registry | done | replay 522 checks; 72 synthetic events; Tier-3 run; registry tests |
| H. API and dashboard | done | API tests incl. auth/rate limit/validation; headless render of 7 pages on real artifacts |
| I. Docker, Azure IaC, CI/CD | written; Bicep compiled + linted | Docker build and CI not executed locally (no Docker); Azure not deployed (no subscription access) |
| J. end-to-end validation, docs | done | e2e test runs synthetic -> features -> train -> registry -> retrain -> API |

## Blockers and external dependencies

- Observed discharge (CWC Bhuntar) not publicly available; GloFAS used. Supply `data/raw/discharge_gauge.csv` to switch.
- DagsHub DVC remote requires a token (HTTP 401); raw data were regenerated from source instead. Run `dvc push` with credentials to update the remote if desired (the regenerated files may differ byte-wise from the DVC-tracked version).
- Azure: needs `az login` to the student subscription; GitHub OIDC variables for CD.
- Docker: needed to build/run the image locally (CI builds it).
- Earth Engine service account: needed for scheduled ingestion in Azure.
- Hi-MAG/ICIMOD lake inventories: download and licence check pending.
