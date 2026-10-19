# Experimental protocol (pre-registered)

Fixed in `configs/forecast.yaml` and this file **before** the first `--final` run. Any change after
the test period has been evaluated must be logged as a protocol deviation at the end of this file.
`artifacts/<mode>/test_access.log` records every time the test period is scored.

## Research questions and hypotheses

- **RQ1.** Do learned models that use snow cover, meteorology and antecedent discharge beat persistence
  and day-of-year climatology for daily discharge at 1, 7 and 30 days?
  - H1a: GBM and LSTM achieve lower QS than climatology at all horizons and lower than persistence at 7 and 30 days.
  - H1b: Persistence is hard to beat at 1 day (strong autocorrelation of a reanalysis series).
- **RQ2.** Are P10-P90 intervals calibrated on held-out years after conformal (CQR) calibration?
  - H2: Calibrated coverage on test lies within 0.70-0.90 for each horizon; monsoon coverage is the most likely to fail.
- **RQ3.** Does a simulated variational quantum circuit (VQC) match capacity-matched classical models on the same task?
  - H3 (null expectation): No significant QS difference in favour of the VQC; any difference is attributable to capacity and optimisation, not quantum effects. A simulator result cannot show quantum advantage.

## Target and its limitation

Observed CWC discharge for Beas at Bhuntar is not publicly available (Indus-basin data are classified
on India-WRIS). The target is **GloFAS v4 reanalysis discharge** (modelled, driven by ERA5) at
31.825 N, 77.125 E, the grid cell on the Beas main stem below the Parvati confluence. Skill is
therefore skill at reproducing GloFAS, not at predicting the real river. GloFAS shows almost no
rise in April-June at this cell, earlier than the snowmelt rise expected for the Beas; this is a
plausible GloFAS snowmelt-timing bias and is not corrected. If `data/raw/discharge_gauge.csv` is
supplied, the same pipeline runs on observed discharge and the reports state `target_is_observed: true`.

## Forecast set-up

- Issue date t; horizons h = 1, 7, 30 days; target = daily mean discharge on t+h (m3/s).
- Availability lags (assumed operational latencies): discharge 1 d, MODIS 1 d, ERA5-Land 5 d. Features at t use only values published by t.
- No numerical weather forecasts are used. Longer horizons rely on basin state (snow, antecedent flow) and season.

## Splits

| period | issue dates | use |
|---|---|---|
| train | 2015-01-01 .. 2020-12-31 (after 75-day warm-up) | fitting |
| calibration | 2021-01-01 .. 2022-12-31 | CQR conformal calibration |
| test | 2023-01-01 .. 2025-12-31 | final, scored once |

Embargo: a sample with issue date t is kept in a period only if t+h is in the same period, so no
target crosses a boundary. Rolling-origin CV for selection: validate on each of 2019, 2020, 2021, 2022
with training on all earlier issue dates (expanding window). Preprocessing statistics (LSTM
standardisation, GBM has none) are fitted on training rows only. LSTM early stopping uses the final
365 days of its own training window.

## Models and tuning budget

- Persistence (seasonal log-ratio spread), climatology (+/-15-day window quantiles).
- LightGBM quantile regression: 4 configurations (listed in config), 3 boosters per horizon.
- Quantile LSTM: 2 configurations, monotone quantile head, pinball loss.
- Selection: lowest mean CV QS over folds and horizons, seed 11 only. Final models: seeds 11, 22, 33, forecast = mean of seed quantiles.
- VQC benchmark: see `docs/quantum_benchmark.md`.

## Metrics

- Deterministic (P50): NSE, KGE (Gupta 2009), MAE, RMSE.
- Probabilistic: QS = mean over tau in {0.1, 0.5, 0.9} of 2 x pinball loss, a 3-point approximation of CRPS (m3/s; coarse). P10-P90 coverage (nominal 0.80) and mean width.
- Undefined values (zero variance, empty sample) are reported as NaN.
- Seasonal breakdown by target month: winter DJF, pre-monsoon MAM, monsoon JJAS, post-monsoon ON.
- Primary metric: test QS per horizon. Comparisons: paired moving-block bootstrap (30-day blocks, 1000 resamples, 95% CI) of per-sample QS differences on identical issue dates.

## Acceptance criteria (governance gate, `configs/governance.yaml`)

Per horizon on the evaluation window: NSE >= 0.7 (h1), 0.4 (h7), 0.0 (h30); coverage in [0.70, 0.90];
QS below climatology; >= 180 samples. Against an incumbent: mean QS ratio <= 0.98. Promotion also
requires a named human approver.

## Protocol deviations

None recorded.
