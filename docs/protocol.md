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

- 2026-10-19, lakes: processing scale changed from 10 m to 20 m before any scores were seen (10 m exceeded Earth Engine interactive limits).
- 2026-10-19, lakes: JRC labels were initially masked outside the historical water extent (only shoreline pixels counted as land). This was fixed before any scores were computed, by unmasking to "not water".
- 2026-10-19, lakes: the held-out lake test split (2021) contained almost no water (0.00076 km2). Scores were reported as non-interpretable; a water-stratified block split is proposed but has **not** been run.
- 2026-10-19, lakes: re-split fixed before re-scoring. Rule: blocks ranked by 2019 (tune-year) JRC water area; wet blocks in groups of 4 get a seeded permutation of train/train/val/test, dry blocks split 50/25/25 at random (seed 42). Years unchanged (JRC GSW 1.4 ends 2021, S2 L2A starts 2019, so no unseen year exists). Caveat: 2021 test-year imagery was already scored once under the old split, so the new test score is not fully blind. Growth flags now use Benjamini-Hochberg q < 0.05 instead of raw p < 0.05. Run done 2026-10-19: test now holds 0.087 km2 of water (475 samples); test IoU 0.11 (low skill, reported as is).
- 2026-10-20, forecasting (registered before the re-run): the first `--final` run failed the gate on coverage (selected gbm_quantile: h7 0.698, h30 0.685; monsoon coverage ~0.5). **Single change:** CQR offsets are fitted per season of the target date (Mondrian CQR; seasons as in `configs/forecast.yaml`; a season with < 60 calibration samples falls back to the pooled offset). Models, features, grids, seeds, splits, selection rule and gate are unchanged. The test period is scored once more and the result is reported whatever it is; no further calibration variants will be tried on test. Caveat: this change was chosen after seeing test coverage, so a pass is weaker evidence than a first-run pass; the first-run results stay in the git history (`reports/real/forecast_results.md` at commit af7ff1b).
  **Result (run 2026-10-20, single test access):** the gate still fails. Selected gbm_quantile coverage h1 0.727, h7 0.701, h30 **0.689** (< 0.70). Monsoon coverage rose (h7 0.47 -> 0.60, h30 0.54 -> 0.68) and test QS fell slightly (h7 8.28 -> 7.72, h30 16.91 -> 16.22), but pre- and post-monsoon coverage stayed ~0.60. Per this registration, no further calibration variants are tried on this test period.
