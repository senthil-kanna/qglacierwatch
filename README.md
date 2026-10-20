# QGlacierWatch

Season-aware probabilistic discharge forecasting (P10/P50/P90 at 1, 7 and 30 days), glacial-lake
monitoring, drift-triggered retraining governance and a fair simulated quantum-classical benchmark
for the Beas River above Bhuntar, Himachal Pradesh (HydroBASINS catchment, 3,532 km2).

> **Read this first.** Long-term observed discharge (CWC, Bhuntar) is not publicly available, so the
> forecast target is **GloFAS v4 modelled discharge**: consolidated reanalysis up to 2023-08-04, and
> operational forecast-derived values from 2023-08-05 (Open-Meteo `seamless_v4`; see
> `docs/protocol_fresh2026.md`). Every skill score measures how well GloFAS is reproduced, not the
> real river. **A consistency check against a state telemetry gauge 3.7 km downstream (Bajoura
> Bridge, HP Water Department via the National Water Data Portal, 737 days 2023-2026) shows GloFAS
> matches it poorly (NSE 0.21; about half the observed flow in 2026; large seasonal biases), and
> our forecasts reach only NSE 0.1-0.3 against it** (`docs/protocol_gauge_check.md`; gauge quality
> unknown, so this is not independent validation). No model has passed the promotion gate, nothing
> is deployed to Azure, and nothing here is a live feed. Synthetic data are used only in tests and
> `demo` mode.

## What is implemented, what ran, what is blocked

| component | implemented | executed on real data (2026-10-19) | depends on | notes |
|---|---|---|---|---|
| Ingest: MODIS MOD10A1, ERA5-Land (Earth Engine), GloFAS (Open-Meteo) | yes | yes, 2015-2025 | EE account | pre-existing scripts, regenerated because the DVC remote needs a token |
| Provenance manifest, schema/range/completeness checks | yes | yes | - | `data/raw/MANIFEST.json` |
| Versioned leakage-safe feature table | yes | yes (`2b46646ce1c0`) | - | availability lags, causal gap filling, embargoed splits |
| Persistence, climatology, LightGBM quantile, quantile LSTM | yes | yes | - | rolling-origin CV, 3 seeds |
| CQR calibration, metrics, seasonal breakdowns, block bootstrap | yes | yes | - | `reports/real/forecast_results.md` |
| Model registry, gate, approval, rollback, audit log | yes | yes (candidates registered; gate failed) | - | no production model |
| Season-aware drift monitors, replay 2016-2025, synthetic perturbations | yes | yes | - | `reports/real/drift_replay.md` |
| Tier-2/3 retraining | yes | Tier 3 once (gate failed) | - | `reports/real/retraining_runs.json` |
| VQC benchmark (PennyLane simulator) + matched classical models | yes | yes, 7 models x 5 seeds | - | `reports/real/quantum_benchmark.md` |
| Glacial-lake segmentation (S2/S1, JRC silver labels) | yes | yes (20 m, 2019-2025): water-stratified split: val IoU 0.37, **test IoU 0.11 (low skill, over-maps water)**; 34 lakes, no area trend, 0 growth flags after BH; **vs Hi-MAG 2017: 17/21 lakes found (88% of area), but matched lake areas ~0.5x Hi-MAG** | EE account | registered v2 attempt (MNDWI, slope, SWIR, SAR variants) did not beat the current rule; no common year with Hi-MAG (ends 2017) |
| REST API (FastAPI, /v1) | yes | locally, on real artifacts | - | `docs/openapi.json` |
| Dashboard (Streamlit, 7 pages) | yes | headless render tests on real artifacts | - | |
| Docker image, compose | yes | **not built locally** (no Docker) | Docker | built and smoke-tested in CI |
| Azure Bicep (Container Apps, ACR/GHCR, Files, Key Vault, budget) | yes | compiled + linted only; **not deployed** | Azure subscription | `docs/deployment.md` |
| CI/CD (GitHub Actions) | yes | **not run yet** (needs a push) | GitHub | |

## Quick start (no credentials, SYNTHETIC demo)

```bash
python -m venv .venv
.venv\Scripts\activate                 # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
set QGW_MODE=demo                      # PowerShell: $env:QGW_MODE="demo"; bash: export QGW_MODE=demo
python -m src.data.synthetic           # writes data/synthetic/ (labelled SYNTHETIC)
python -m src.features.build
python -m src.pipeline.train --quick --final
pytest                                 # 81 offline tests
uvicorn api.main:app --port 8000       # http://localhost:8000/docs
streamlit run dashboard/streamlit_app.py
```

## Real-data workflow

```bash
earthengine authenticate                     # once; set EE_PROJECT if not ee-senthil-hydro
python -m src.ingest.earth_engine            # MODIS + ERA5-Land basin means, basin polygon
python -m src.ingest.discharge               # GloFAS v4 (or data/raw/discharge_gauge.csv if present)
python -m src.ingest.provenance              # record / verify SHA-256 manifest
python -m src.features.build
python -m src.pipeline.train --final         # CV, fit, calibrate, score test ONCE, register candidate
python -m src.drift.replay                   # replay + synthetic perturbation evaluation
python -m src.quantum.benchmark
python -m src.lakes.pipeline                 # Earth Engine; ~30+ min
python -m src.registry.registry list
python -m src.registry.registry promote --model-id <id> --approver "Name" --reason "..."   # refuses if gate fails
```

## Key results (real data, test period 2023-2025)

Probabilistic score QS (3-quantile CRPS approximation, m3/s; lower is better), calibrated intervals:

| lead | persistence | climatology | LightGBM | LSTM |
|---|---|---|---|---|
| 1 d | **2.83** | 18.13 | 4.72 | 3.92 |
| 7 d | **7.83** | 18.23 | 8.28 | 10.71 |
| 30 d | 22.44 | 18.57 | 16.91 | **16.13** |

- Persistence is best at 1 day (significantly better than the LSTM); at 7 days GBM and persistence are statistically indistinguishable; at 30 days learned models are better on average but block-bootstrap CIs against climatology include zero.
- Monsoon intervals undercover (0.47-0.69); 2025 flows exceed the training range. The gate rejected every candidate on coverage. A registered per-season CQR re-run raised monsoon coverage (to 0.60-0.68 for GBM) but still missed the gate at 30 d (0.689 < 0.70).
- **Fresh 2026 test** (registered before data, scored once; `docs/protocol_fresh2026.md`): GBM NSE 0.994 / 0.980 / 0.962 at 1 / 7 / 30 d, but intervals over-cover (0.938 and 0.955 > 0.90) because calibration on the extreme 2025 flows widened them for a low-flow 2026. Gate failed in the opposite direction. The VQC was again worse than all classical baselines.
- The GloFAS target is reanalysis only to 2023-08-04; later values are forecast-derived (median 2.4% lower, July 11% lower). Corrected in all docs.
- Season-blind drift detection alarms on 99.8% of weekly checks; the season-aware monitor on 4.9%.
- The simulated VQC (QS 28.9) is worse than a 15-parameter linear model on the same 4 inputs (10.1) and than climatology. No quantum advantage is claimed or testable on a simulator.

Full tables: [forecast](reports/real/forecast_results.md), [drift](reports/real/drift_replay.md),
[quantum](reports/real/quantum_benchmark.md), [lakes](reports/real/lake_analysis.md).

## Documentation

- [Experimental protocol](docs/protocol.md) (pre-registered hypotheses, splits, budgets, metrics)
- [Architecture and data-flow diagrams](docs/architecture.md)
- [Data-access and licensing audit](docs/data_access.md) | [data card](docs/data_card.md) | [model card](docs/model_card.md)
- [Drift, retraining and governance](docs/governance.md)
- [Quantum benchmark](docs/quantum_benchmark.md) | [Lakes](docs/lakes.md)
- [Deployment, Azure cost model, security](docs/deployment.md)
- API: `docs/openapi.json`, or `/docs` on a running server

## API summary

| route | purpose |
|---|---|
| `GET /health`, `/v1/health` | status, serving model, data freshness, problems |
| `GET /v1/forecast[?issue_date=YYYY-MM-DD]` | P10/P50/P90 at 1/7/30 d from the serving model, with model id, dataset id, target source, warnings |
| `GET /v1/hindcast?issue_date=&model=` | stored evaluation forecasts labelled `train_in_sample` / `calibration` / `test` |
| `GET /v1/models` | registry state |
| `GET /v1/reports/{forecast_results,drift_replay,quantum_benchmark,lake_analysis}` | result reports |

Errors are JSON `{"error", "detail"}` with 401/404/422/429/503. Set `QGW_API_KEY` to require `X-API-Key`.

## Limitations and future work

- **Observed discharge**: the only open gauge found near the outlet (Bajoura Bridge, HP Water Department telemetry via NWDP) covers 2023-07..2026-09 with gaps (737 of 1,173 days), has unknown method, rating curve and quality control, and its raw data are not redistributed here (terms unclear). It shows GloFAS is a weak stand-in at this site (NSE 0.21, seasonal biases of 0.5-2x), so forecasts of GloFAS are not forecasts of the river. A long, quality-controlled record (CWC Bhuntar; see `docs/gauge_data_request.md`) is needed before retraining on observed flow; the pipeline switches automatically when `data/raw/discharge_gauge.csv` exists.
- **Weather forecasts**: add ECMWF/GEFS precipitation and temperature forecasts for 7-30 day leads; current long-lead skill relies on basin state only.
- **Calibration under shift**: per-season CQR was tried once (registered, 2026-10-20) and still missed the gate at 30 d. Adaptive conformal inference (ACI) or a longer calibration window needs a fresh, unseen test year before it can be judged fairly.
- **Spatial detail**: elevation-band snow cover and temperature lapse rates instead of basin means.
- **Lakes**: Hi-MAG (CC BY 4.0) is now compared (`reports/real/himag_comparison.md`) but ends in 2017; a post-2019 reference (manual annotation or a newer inventory) is still needed for pixel-level validation; per-lake uncertainty.
- **Quantum**: trainable input scaling, longer schedules and noise models; a hardware run would test feasibility only.
- **Operations**: rolling data versions for operational updates beyond 2025; deploy and monitor on Azure.
