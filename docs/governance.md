# Drift monitoring, tiered retraining and governance

Results: `reports/real/drift_replay.md`, `reports/real/retraining_runs.json`, registry audit log in
`artifacts/real/registry/audit.jsonl`.

## Monitors (`src/drift/monitor.py`, thresholds in `configs/drift.yaml`)

| kind | what | detector |
|---|---|---|
| data_quality | missing-day share per source in the 30-day window | rule (thresholds per source) |
| pipeline | identical consecutive values of temperature, discharge, non-zero snow fraction (stuck sensor) | rule (>= 5 days) |
| covariate | 7 model inputs (t_mean7, p_sum7, pdd7, melt7, snow_frac, swe_change30, logq0) | baseline and season-aware |
| prediction | log P50 at 7 days | baseline and season-aware |
| residual | window QS ratio vs reference and P10-P90 coverage binomial test, h = 1 and 7 days | baseline (all past residuals) and season-aware (target day-of-year +/- 15 d) |

Both covariate detectors use the same Benjamini-Hochberg FDR (q = 0.05) across features at each
check, the same persistence rule (2 consecutive weekly checks) and the same severity mapping. Only
the reference differs. Season-aware covariate tests need >= 4 past years of the same calendar window,
so they start in 2019. Residual checks only use observations already available at the check date
(1-day discharge lag) and out-of-sample forecasts (calibration and test periods).

## Replay findings (real inputs, 522 weekly checks 2016-2025)

| monitor | checks evaluated | with alert | alert rate |
|---|---|---|---|
| covariate, baseline (season-blind KS) | 522 | 521 | 0.998 |
| covariate, season-aware | 350 | 17 | 0.049 |
| prediction, baseline | 230 | 225 | 0.978 |
| prediction, season-aware | 49 | 11 | 0.224 |
| residual, baseline | 248 | 83 | 0.335 |
| residual, season-aware | 204 | 63 | 0.309 |
| data quality | 522 | 4 | 0.008 |

The season-blind monitor treats every monsoon and melt transition as drift. The season-aware
monitor alerts on about 5% of checks. Residual alerts concentrate in the 2023-2025 monsoons, where
held-out coverage is genuinely poor; they are consistent with the gate failures, not false alarms
in any testable sense. Real-data replay has no ground-truth drift labels, so these rates describe
behaviour, not accuracy.

## Controlled synthetic perturbations (24 random onsets each, 2020-2025)

| event (SYNTHETIC) | detector | recall | median delay | clean windows with alarm | event precision |
|---|---|---|---|---|---|
| +2.5 degC temperature sensor bias, 90 d | season-aware | 0.42 | 42 d | 5/24 | 0.50 |
| snow sensor dropout to 0, 45 d | season-aware | 0.83 | 24 d | 12/24 | 0.40 |
| rating-curve shift x1.35 | season-aware | 1.00 | 14 d | 21/24 | 0.12 |
| any of the above | baseline | 1.00 | 0 d | 24/24 | 0.00 |

The baseline "detects" everything only because it alarms in every window anyway. The season-aware
monitor's low precision for the rating shift reflects residual alerts that already occur without the
perturbation in the poorly calibrated test years. The rating-shift experiment scales verification
discharge after onset while keeping stored forecasts fixed; in operation the model's lagged-discharge
inputs would shift too.

## Tiered retraining (`src/drift/policy.py`, `src/pipeline/retrain.py`)

| tier | trigger | action |
|---|---|---|
| 1 | data_quality or pipeline alert | fix inputs; no model change |
| 2 | persistent residual alert driven by coverage only | refit CQR on the latest labelled window |
| 3 | persistent residual alert with QS ratio > 2 | retrain a candidate with the incumbent's configuration (no new tuning) |
| 4 | gate passed | manual promotion by a named approver; rollback available |

Season-aware covariate drift alone only raises monitoring (tier 0). Candidates and incumbents are
always scored on the same recent window that neither was fitted or calibrated on.

Executed: one Tier-3 run (decision simulated at the end of 2024 after 6 Tier-3 recommendations
that year): train 2015-2023, calibrate 2024, evaluate 2025. Mean QS on 2025: candidate 13.17 vs
incumbent 17.71. Gate **failed** (30-day coverage 0.633 < 0.70); candidate not promoted.

## Promotion gate (`configs/governance.yaml`)

Per horizon: NSE floors (0.7 / 0.4 / 0.0), coverage in [0.70, 0.90], QS below climatology, >= 180
samples; versus incumbent on the same window: mean QS ratio <= 0.98. Promotion requires the gate
and a non-empty approver name; there is no force flag. Every register, gate, promote, rejected
promotion and rollback is appended to `audit.jsonl`. Tests in `tests/test_registry.py` cover
"never promote a worse model", approval, window mismatch and rollback.

Rationale for thresholds: coverage band of +/- 0.10 around nominal 0.80 allows sampling variation
for ~1,000 daily samples with strong autocorrelation; the 2% improvement margin avoids churning on
noise; NSE floors encode "clearly useful" at short leads and "no worse than the mean" at 30 days.
