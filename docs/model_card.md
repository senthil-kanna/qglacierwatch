# Model card: QGlacierWatch discharge forecaster

All numbers below are copied from `reports/real/forecast_results.md` (run 2026-10-19, dataset
`2b46646ce1c0`). Regenerate with `python -m src.pipeline.train --mode real --final`.

## Intended use

Probabilistic daily discharge guidance (P10/P50/P90) for the Beas above Bhuntar at 1, 7 and 30
days, for research on snowmelt-driven forecasting and for monitoring/governance experiments.
**Not for flood warning or operational decisions**: the target is GloFAS reanalysis (modelled), no
weather forecasts are used, and no production model has passed the promotion gate.

## Models

| model | description | capacity |
|---|---|---|
| persistence | last available discharge; seasonal log-ratio spread | - |
| climatology | +/- 15-day day-of-year quantiles (training years) | - |
| gbm_quantile | LightGBM, one booster per quantile, log target; selected config `num_leaves=15, lr=0.03, n_estimators=800, min_child_samples=40`; 3 seeds averaged | ~35k leaf values per horizon (3 boosters); 0.8-3.4 s training per seed |
| quantile_lstm | 1-layer LSTM (64 hidden, dropout 0.1), 60-day sequence, monotone quantile head; 3 seeds averaged | 23,939 parameters; 1.7-8.5 s training per seed (CPU, early stopping) |

All intervals are conformal-calibrated (CQR) on 2021-2022.

## Inputs

34 features at issue date t, built from information available at t (lags: discharge 1 d, MODIS 1 d,
ERA5-Land 5 d): lagged and smoothed log discharge, 3/7/30-day temperature, precipitation, rain,
positive degree-days, snowfall, ERA5 snowmelt, 30-day SWE change, MODIS snow fraction (causally
filled, with its age), cloud-free share, season (issue and target day of year), and two
interactions motivated by degree-day melt (PDD x snow fraction, rain x snow fraction).

## Held-out performance (test 2023-2025, calibrated)

| h | best by QS | persistence QS | gbm QS | lstm QS | climatology QS | gbm cov80 | lstm cov80 |
|---|---|---|---|---|---|---|---|
| 1 | persistence | 2.83 | 4.72 | 3.92 | 18.13 | 0.709 | 0.803 |
| 7 | persistence (gbm n.s. different) | 7.83 | 8.28 | 10.71 | 18.23 | 0.698 | 0.745 |
| 30 | lstm (CIs include 0 vs climatology) | 22.44 | 16.91 | 16.13 | 18.57 | 0.685 | 0.671 |

Paired block bootstrap: at 1 day the LSTM is significantly worse than persistence (+1.09 QS, 95% CI
[0.12, 2.61]); at 7 days GBM vs persistence +0.45 [-2.29, 4.43]; at 30 days LSTM vs climatology
-2.44 [-5.18, 0.10].

## Known failure modes

- Monsoon (JJAS) intervals are too narrow on test: coverage 0.47-0.69 for learned models with pooled CQR; 0.60-0.77 with per-season CQR (deviation 2026-10-20 in `docs/protocol.md`).
- With per-season CQR (one registered re-run) the GBM candidate still **failed the gate**: coverage 0.727 / 0.701 / **0.689** at 1 / 7 / 30 d. Pre- and post-monsoon coverage (~0.60) is now the weak spot.
- 2025 is outside the training range (GloFAS annual max 366 m3/s vs <= 316 in training years); residual drift alerts fire through 2025.
- The registered GBM candidate **failed the gate** (coverage 0.698 at 7 d and 0.685 at 30 d, below 0.70). A Tier-3 retrain (train 2015-2023, calibrate 2024, evaluate 2025) lowered mean QS on 2025 from 17.71 to 13.17 but still failed (coverage 0.633 at 30 d). No model is in production; the API serves the newest candidate and labels it `unpromoted_candidate`.
- Basin-mean remote-sensing variables hide elevation-dependent melt; ERA5-Land's coarse grid misrepresents the steep terrain.

## Ethical and operational considerations

A forecast that looks authoritative but reproduces a biased reanalysis could mislead users about
real river levels. Every API response and dashboard view states the target source and whether it
is observed.
