# Gauge check: Bajoura Bridge (generated 2026-10-20T09:10:44+00:00)

Data: Himachal Pradesh Water Department, via National Water Data Portal (NWIC, Ministry of Jal Shakti).

Consistency check against a state telemetry gauge, not independent validation: method, rating curve and quality control are unknown (`docs/protocol_gauge_check.md`). Bajoura is 3.7 km downstream of the catchment outlet. Raw data are not redistributed.

Readings: 75,395 (6,177 invalid, 0 duplicate timestamps). Valid days (>= 48 readings): 737 of 1173 calendar days 2023-07-14..2026-09-28. Flagged days: zero 21, spike 6, flatline 39, extreme 4 (2024-08-01 (767), 2026-07-11 (679), 2026-08-07 (649), 2026-08-08 (636)).

## C1 GloFAS vs observed (daily)

| subset | n | obs mean | GloFAS mean | bias ratio | median ratio | r | NSE | KGE |
|---|---|---|---|---|---|---|---|---|
| all | 737 | 134.6 | 111.4 | 0.83 | 1.09 | 0.52 | 0.21 | 0.40 |
| unflagged | 672 | 137.3 | 114.5 | 0.83 | 1.04 | 0.53 | 0.21 | 0.44 |
| 2023_2025 | 523 | 131.9 | 128.0 | 0.97 | 1.16 | 0.53 | 0.20 | 0.49 |
| 2026 | 214 | 141.4 | 70.8 | 0.50 | 0.56 | 0.78 | 0.22 | 0.15 |

| season (all days) | n | bias ratio | median ratio | r | NSE |
|---|---|---|---|---|---|
| winter | 159 | 1.96 | 1.43 | -0.47 | -4.87 |
| pre_monsoon | 186 | 0.49 | 0.59 | -0.36 | -0.82 |
| monsoon | 303 | 0.75 | 0.80 | 0.13 | -0.52 |
| post_monsoon | 89 | 2.18 | 2.28 | 0.62 | -14.40 |

## C2a Original forecasts (test 2023-2025)

| model | h | n | NSE vs gauge | KGE vs gauge | QS vs gauge | cov80 vs gauge | NSE vs GloFAS (same dates) | cov80 vs GloFAS |
|---|---|---|---|---|---|---|---|---|
| climatology | 1 | 523 | 0.30 | 0.38 | 52.77 | 0.22 | 0.80 | 0.83 |
| climatology | 7 | 523 | 0.30 | 0.38 | 52.77 | 0.22 | 0.80 | 0.83 |
| climatology | 30 | 523 | 0.30 | 0.38 | 52.86 | 0.22 | 0.80 | 0.82 |
| gbm_quantile | 1 | 523 | 0.22 | 0.46 | 66.91 | 0.07 | 0.97 | 0.76 |
| gbm_quantile | 7 | 523 | 0.19 | 0.41 | 65.31 | 0.13 | 0.93 | 0.70 |
| gbm_quantile | 30 | 523 | 0.19 | 0.31 | 57.25 | 0.24 | 0.80 | 0.75 |
| persistence | 1 | 523 | 0.14 | 0.45 | 71.40 | 0.07 | 0.99 | 0.77 |
| persistence | 7 | 523 | -0.02 | 0.34 | 72.01 | 0.13 | 0.92 | 0.76 |
| persistence | 30 | 523 | -0.60 | -0.08 | 79.97 | 0.20 | 0.34 | 0.68 |
| quantile_lstm | 1 | 523 | 0.21 | 0.46 | 67.83 | 0.09 | 0.99 | 0.85 |
| quantile_lstm | 7 | 523 | 0.23 | 0.42 | 60.49 | 0.22 | 0.91 | 0.78 |
| quantile_lstm | 30 | 523 | 0.30 | 0.45 | 55.09 | 0.25 | 0.86 | 0.73 |

## C2b Fresh 2026 forecasts (test Jan-Sep 2026)

| model | h | n | NSE vs gauge | KGE vs gauge | QS vs gauge | cov80 vs gauge | NSE vs GloFAS (same dates) | cov80 vs GloFAS |
|---|---|---|---|---|---|---|---|---|
| climatology | 1 | 213 | 0.38 | 0.26 | 63.19 | 0.08 | 0.89 | 0.84 |
| climatology | 7 | 207 | 0.37 | 0.26 | 63.98 | 0.08 | 0.90 | 0.86 |
| climatology | 30 | 184 | 0.31 | 0.25 | 67.57 | 0.20 | 0.90 | 0.94 |
| gbm_quantile | 1 | 213 | 0.20 | 0.14 | 87.70 | 0.00 | 0.99 | 0.93 |
| gbm_quantile | 7 | 207 | 0.18 | 0.14 | 84.82 | 0.00 | 0.98 | 0.86 |
| gbm_quantile | 30 | 184 | 0.21 | 0.18 | 74.93 | 0.14 | 0.96 | 0.99 |
| persistence | 1 | 213 | 0.19 | 0.13 | 89.88 | 0.01 | 0.99 | 0.85 |
| persistence | 7 | 207 | 0.08 | 0.07 | 86.94 | 0.01 | 0.93 | 0.81 |
| persistence | 30 | 184 | -0.44 | -0.30 | 95.02 | 0.11 | 0.32 | 0.77 |
| quantile_lstm | 1 | 213 | 0.22 | 0.15 | 87.67 | 0.01 | 0.99 | 0.83 |
| quantile_lstm | 7 | 207 | 0.23 | 0.18 | 81.82 | 0.00 | 0.97 | 0.79 |
| quantile_lstm | 30 | 184 | 0.12 | 0.14 | 77.77 | 0.14 | 0.97 | 0.95 |
