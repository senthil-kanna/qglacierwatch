# Drift replay (real mode)

Real-data replay has no ground-truth drift labels; alert rates there describe behaviour, not accuracy. Accuracy is measured only on controlled synthetic perturbations.

## Historical replay (real inputs)

Weekly checks: 522, 2016-01-01 .. 2025-12-26.

| kind | detector | checks evaluated | checks with alert | alert rate | alerts by season |
|---|---|---|---|---|---|
| covariate | baseline | 522 | 521 | 0.998 | {'monsoon': 175, 'post_monsoon': 86, 'pre_monsoon': 132, 'winter': 128} |
| covariate | season_aware | 350 | 17 | 0.049 | {'monsoon': 6, 'post_monsoon': 4, 'pre_monsoon': 5, 'winter': 2} |
| data_quality | rule | 522 | 4 | 0.008 | {'post_monsoon': 4} |
| prediction | baseline | 230 | 225 | 0.978 | {'monsoon': 73, 'post_monsoon': 43, 'pre_monsoon': 53, 'winter': 56} |
| prediction | season_aware | 49 | 11 | 0.224 | {'post_monsoon': 7, 'winter': 4} |
| residual | baseline | 248 | 83 | 0.335 | {'monsoon': 59, 'post_monsoon': 4, 'pre_monsoon': 20} |
| residual | season_aware | 204 | 63 | 0.309 | {'monsoon': 31, 'post_monsoon': 6, 'pre_monsoon': 25, 'winter': 1} |

## Controlled SYNTHETIC perturbations (not real events)

| event | detector | recall | median delay (d) | missed | clean windows with alarm | event precision |
|---|---|---|---|---|---|---|
| temperature_bias | baseline | 1.00 (24/24) | 0 | 0 | 24/24 | 0.00 |
| temperature_bias | season_aware | 0.42 (10/24) | 42 | 14 | 5/24 | 0.50 |
| snow_sensor_dropout | baseline | 1.00 (24/24) | 0 | 0 | 24/24 | 0.00 |
| snow_sensor_dropout | season_aware | 0.83 (20/24) | 24 | 4 | 12/24 | 0.40 |
| discharge_rating_shift | baseline | 1.00 (24/24) | 0 | 0 | 24/24 | 0.00 |
| discharge_rating_shift | season_aware | 1.00 (24/24) | 14 | 0 | 21/24 | 0.12 |

## Documented real events (context only)

- July 2023 extreme rainfall and flooding in Himachal Pradesh (Beas valley affected) (2023-07-07..2023-07-12): alerts within 30 days after start: ['covariate/baseline/logq0', 'covariate/baseline/melt7', 'covariate/baseline/p_sum7', 'covariate/baseline/pdd7', 'covariate/baseline/snow_frac', 'covariate/baseline/swe_change30', 'covariate/baseline/t_mean7', 'prediction/baseline/log_p50_h7', 'residual/baseline/h1', 'residual/baseline/h7', 'residual/season_aware/h1', 'residual/season_aware/h7']
