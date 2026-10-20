# Fresh 2026 forecast evaluation: registered protocol

Registered 2026-10-20, **before** any 2026 data were ingested into the project and before any model
was trained or scored on 2026. Commits after this file may implement it but not change it; any
deviation is logged at the end with its reason, and if a change is made after 2026 results are seen,
2026 is labelled **consumed** and no further untouched-test claim is made on it.

## Why a new test

The 2023-2025 test period has been scored twice (first run; registered per-season CQR re-run), and
the per-season CQR choice was made after seeing it. Jan-Sep 2026 is a period no model or design
decision has used.

## Data verification (done before registration, no model involved)

| input | product | 2026 coverage checked 2026-10-20 |
|---|---|---|
| snow | MODIS/061/MOD10A1 (Earth Engine) | 273/273 days Jan-Sep (images to 2026-10-17) |
| meteorology | ECMWF/ERA5_LAND/DAILY_AGGR (Earth Engine) | 273/273 days Jan-Sep (images to 2026-10-06) |
| discharge | GloFAS v4 via Open-Meteo, `seamless_v4` | 273/273 days, none missing |

**Target product change (found during verification).** At our cell the stored series equals
`seamless_v4` on all 4,018 days 2015-2025. `seamless_v4` equals `consolidated_v4` (reanalysis)
up to 2023-08-04 and equals `forecast_v4` (operational, forecast-derived) from 2023-08-05; the
consolidated product ends 2025-05-31 and does not cover 2026. Where both exist (2023-08-05 to
2025-05-31, 660 differing days), the forecast-derived series is lower: median ratio 0.976, July
0.89, August 0.92; NSE between the two 0.94. Earlier reports called the whole series "reanalysis";
that is corrected in the docs. For 2026 only the forecast-derived product exists, so:

- **Target** = `seamless_v4` as stored: consolidated reanalysis to 2023-08-04, forecast-derived
  afterwards. 2026 targets are forecast-derived.
- Calibration (2024-2025) is almost entirely forecast-derived, i.e. the same product as the test.

## Data version

- New root `data/fresh2026/` (git-ignored; DVC-tracked later). Raw files are byte-for-byte copies of
  the current `data/raw/` files for 2015-2025 (SHA-256 checked against `data/raw/MANIFEST.json`),
  with **2026-01-01 to 2026-09-30 appended** from the same products and the same code paths
  (`src.ingest.earth_engine` statistics; `src.ingest.discharge.fetch_glofas`). No 2015-2025 value
  is re-downloaded or changed. Downloads end at 2026-09-30 so no future seasonal-forecast values of
  `seamless_v4` enter the data.
- Stability check (reported, not used for any decision): re-fetching 2025 discharge and comparing
  with the stored values.
- Separate outputs: `QGW_ARTIFACTS=artifacts/fresh2026`, `QGW_REPORTS=reports/fresh2026`, so the
  existing registry and reports are not touched.

## Splits (issue dates; embargo as in `docs/protocol.md`: t+h must stay inside the period)

| period | issue dates | use |
|---|---|---|
| train | 2015-01-01 .. 2023-12-31 (after the 75-day warm-up) | fitting |
| calibration | 2024-01-01 .. 2025-12-31 | per-season CQR offsets |
| test | 2026-01-01 .. 2026-09-30 | scored **once** |

Model selection: rolling-origin CV on validation years 2020, 2021, 2022, 2023 (all before
calibration and test). Everything else unchanged from `configs/forecast.yaml` and
`docs/protocol.md`: horizons 1/7/30 d, features and availability lags, model families and grids
(persistence, climatology, LightGBM quantile 4 configs, quantile LSTM 2 configs), seeds 11/22/33,
selection rule (lowest mean CV QS), per-season CQR (min 60 samples per season), metrics (NSE, KGE,
MAE, RMSE, QS, P10-P90 coverage and width, seasonal breakdown), paired block bootstrap, and the
governance gate (`configs/governance.yaml`). Implemented as an overlay
`configs/fresh2026/forecast.yaml` changing only `splits` and `cv_validation_years`.

The quantum benchmark (`src.quantum.benchmark`, protocol in `docs/quantum_benchmark.md`) is re-run
on the same splits; its own settings are unchanged.

## Expected sample sizes and season coverage

Test target dates fall in Jan-Sep 2026: winter = Jan-Feb only, pre-monsoon Mar-May, monsoon Jun-Sep,
no post-monsoon. Test samples per horizon about 273 - h (h30: about 243, above the gate's 180).

## Commands (run once, in this order)

```powershell
$env:QGW_MODE="real"; $env:QGW_DATA="data/fresh2026"; $env:QGW_ARTIFACTS="artifacts/fresh2026"
$env:QGW_REPORTS="reports/fresh2026"; $env:QGW_CONFIG_OVERLAY="configs/fresh2026"
python -m src.ingest.extend --until 2026-09-30        # copy 2015-2025 raw + append 2026
python -m src.ingest.provenance                        # manifest for the new data version
python -m src.features.build --mode real
python -m src.pipeline.train --mode real --final       # CV, fit, calibrate, test once, gate
python -m src.quantum.benchmark --mode real
```

## Reporting

All results go to `reports/fresh2026/real/` and are reported whatever they are, with sample counts,
actual evaluation dates, missing observations, seeds, software versions, the code commit and the
commands above.

## Results (single test access 2026-10-20T07:53:38Z; dataset 07aa2d700953; code 75251b5)

Full tables: `reports/fresh2026/real/forecast_results.md`, `quantum_benchmark.md`. Test target
dates 2026-01-02..2026-09-30 (h1: 272 samples, h7: 266, h30: 243); no missing observations.
Selected by CV: gbm_quantile (`num_leaves 7, lr 0.05, 600 trees, min_child_samples 40`; CV QS
6.410) over quantile_lstm (6.474). Seeds 11/22/33. Software: Python 3.12.6, numpy 2.5.4, pandas
3.0.6, LightGBM 4.7.0, torch 2.14.1+cpu, scikit-learn 1.9.1, scipy 1.18.1, earthengine-api 1.7.48,
PennyLane 0.45.1; Windows 11.

| model | h | NSE | KGE | MAE | QS | cov80 | width80 |
|---|---|---|---|---|---|---|---|
| persistence | 1 / 7 / 30 | 0.993 / 0.947 / 0.521 | 0.991 / 0.952 / 0.643 | 3.02 / 9.27 / 29.86 | 1.87 / 5.32 / 15.59 | 0.860 / 0.827 / 0.811 | 9.6 / 30.4 / 72.6 |
| climatology | 1 / 7 / 30 | 0.916 / 0.918 / 0.919 | 0.819 / 0.817 / 0.812 | 13.68 / 13.55 / 13.85 | 9.27 / 9.14 / 9.55 | 0.871 / 0.895 / 0.955 | 65.9 / 67.0 / 73.4 |
| **gbm_quantile** | 1 / 7 / 30 | 0.994 / 0.980 / 0.962 | 0.978 / 0.977 / 0.928 | 2.36 / 5.82 / 9.56 | 1.89 / 4.27 / 8.32 | **0.938** / 0.887 / **0.955** | 16.1 / 32.9 / 72.7 |
| quantile_lstm | 1 / 7 / 30 | 0.995 / 0.975 / 0.960 | 0.985 / 0.907 / 0.917 | 2.80 / 6.58 / 10.14 | 2.01 / 4.59 / 8.29 | 0.864 / 0.820 / 0.947 | 15.1 / 33.1 / 73.0 |

- **Gate: failed**, now on *over*-coverage: gbm_quantile P10-P90 coverage 0.938 (1 d) and 0.955
  (30 d) exceed 0.90; 7 d (0.887) passes; NSE floors and "beats climatology" pass at all horizons.
  No model is promoted.
- **Skill:** learned models beat climatology at 1 and 7 days (bootstrap CIs exclude 0) and beat
  persistence at 30 days (gbm -7.27 QS, CI [-15.6, -0.33]). At 1 day nothing beats persistence
  (H1b holds). At 30 days the gain over climatology is not significant (CI [-3.84, 0.88]).
- **Why the intervals are wide (descriptive, read-only):** the uncalibrated quantiles under-covered
  badly in calibration 2024-2025 (0.65 / 0.48 / 0.35), partly because 2025 was an extreme
  high-flow year (mean 132 m3/s vs ~95 typical; peak 366). CQR widened the intervals accordingly
  (30 d log offsets 0.09-0.37 by season). 2026 was a low-flow year (mean 83, peak 221), so the same
  widening over-covers. This is the non-exchangeability caveat of conformal calibration across
  hydrological regimes, observed directly.
- **Quantum benchmark (h = 7 d, 4 PCA inputs, 5 seeds):** VQC test QS 15.9 +/- 3.0, worse than
  linear (6.46), capacity-matched MLP (7.16) and large MLP (6.58), paired t p <= 0.005 against all
  three (Wilcoxon p = 0.0625, the minimum attainable with 5 seeds). Consistent with H3; a noiseless
  simulator result says nothing about quantum advantage.
- **2026 is now consumed.** No setting is changed in response to these results. A further claim
  needs a later unseen period (e.g. Oct 2026 onward) under a new registered protocol.

## Deviations and procedural notes

- 2026-10-20 (procedural, before any model ran): `src.features.build` was first run without
  `QGW_CONFIG_OVERLAY`, so the feature table ended 2025-12-31 (dataset 2b46646ce1c0 inside
  `data/fresh2026`). It was deleted and rebuilt with the overlay (dataset 07aa2d700953, issue dates
  to 2026-09-30). No model was trained or scored in between.
- Data version built 2026-10-20: +273 rows each for MODIS, ERA5-Land and discharge
  (2026-01-01..2026-09-30), no missing dates; MODIS has 83 days without a usable snow fraction
  (cloud), handled as in earlier years. Stability check: 0 of 365 stored 2025 discharge values
  changed upstream.
