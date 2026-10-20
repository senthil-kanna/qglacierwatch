# Forecast results (real mode)

Target: `GloFAS_v4@31.825,77.125` (MODELLED reanalysis, not observed discharge).
Dataset `2b46646ce1c0`, generated 2026-10-20T05:38:21+00:00, code `9045c2afec2621d3cfd6cf1097926ac1d4783d96-dirty`.

## Held-out test period (calibrated intervals)

| model | h | n | NSE | KGE | MAE | RMSE | QS | cov80 | width80 | raw cov80 |
|---|---|---|---|---|---|---|---|---|---|---|
| persistence | 1 | 1095 | 0.990 | 0.995 | 4.57 | 9.05 | 2.83 | 0.760 | 11.0 | 0.765 |
| climatology | 1 | 1095 | 0.774 | 0.625 | 26.03 | 43.55 | 17.84 | 0.753 | 50.2 | 0.791 |
| gbm_quantile | 1 | 1095 | 0.974 | 0.915 | 6.09 | 14.87 | 4.55 | 0.727 | 14.5 | 0.613 |
| quantile_lstm | 1 | 1095 | 0.985 | 0.937 | 5.56 | 11.28 | 3.85 | 0.802 | 15.9 | 0.784 |
| persistence | 7 | 1089 | 0.940 | 0.970 | 14.19 | 22.55 | 7.85 | 0.743 | 30.3 | 0.725 |
| climatology | 7 | 1089 | 0.774 | 0.625 | 26.17 | 43.68 | 17.92 | 0.751 | 50.5 | 0.790 |
| gbm_quantile | 7 | 1089 | 0.939 | 0.849 | 11.00 | 22.60 | 7.72 | 0.701 | 24.6 | 0.476 |
| quantile_lstm | 7 | 1089 | 0.908 | 0.788 | 15.51 | 27.79 | 10.34 | 0.741 | 33.4 | 0.611 |
| persistence | 30 | 1066 | 0.472 | 0.737 | 47.02 | 67.05 | 22.48 | 0.665 | 76.7 | 0.702 |
| climatology | 30 | 1066 | 0.771 | 0.624 | 26.73 | 44.16 | 18.26 | 0.744 | 51.2 | 0.785 |
| gbm_quantile | 30 | 1066 | 0.797 | 0.659 | 24.68 | 41.56 | 16.22 | 0.689 | 54.4 | 0.329 |
| quantile_lstm | 30 | 1066 | 0.833 | 0.732 | 22.10 | 37.69 | 15.79 | 0.674 | 46.3 | 0.696 |

## Seasonal QS on test (calibrated)

| model | h | winter | pre_monsoon | monsoon | post_monsoon |
|---|---|---|---|---|---|
| persistence | 1 | 0.68 (n=270, cov 0.80) | 0.89 (n=276, cov 0.64) | 6.34 (n=366, cov 0.81) | 1.93 (n=183, cov 0.80) |
| persistence | 7 | 2.07 (n=264, cov 0.82) | 2.53 (n=276, cov 0.57) | 16.01 (n=366, cov 0.77) | 7.87 (n=183, cov 0.83) |
| persistence | 30 | 9.28 (n=241, cov 0.69) | 5.25 (n=276, cov 0.69) | 38.74 (n=366, cov 0.71) | 33.35 (n=183, cov 0.50) |
| climatology | 1 | 5.59 (n=270, cov 0.75) | 3.53 (n=276, cov 0.96) | 32.21 (n=366, cov 0.64) | 28.73 (n=183, cov 0.67) |
| climatology | 7 | 5.66 (n=264, cov 0.74) | 3.55 (n=276, cov 0.96) | 32.21 (n=366, cov 0.64) | 28.73 (n=183, cov 0.67) |
| climatology | 30 | 5.96 (n=241, cov 0.73) | 3.57 (n=276, cov 0.94) | 32.21 (n=366, cov 0.64) | 28.73 (n=183, cov 0.67) |
| gbm_quantile | 1 | 0.53 (n=270, cov 0.81) | 0.95 (n=276, cov 0.60) | 11.57 (n=366, cov 0.74) | 1.84 (n=183, cov 0.77) |
| gbm_quantile | 7 | 1.02 (n=264, cov 0.86) | 2.63 (n=276, cov 0.64) | 18.44 (n=366, cov 0.60) | 3.62 (n=183, cov 0.77) |
| gbm_quantile | 30 | 3.20 (n=241, cov 0.86) | 6.39 (n=276, cov 0.61) | 31.56 (n=366, cov 0.68) | 17.52 (n=183, cov 0.60) |
| quantile_lstm | 1 | 0.53 (n=270, cov 0.83) | 1.20 (n=276, cov 0.89) | 8.20 (n=366, cov 0.77) | 4.06 (n=183, cov 0.68) |
| quantile_lstm | 7 | 1.67 (n=264, cov 0.74) | 3.10 (n=276, cov 0.93) | 20.69 (n=366, cov 0.72) | 13.05 (n=183, cov 0.50) |
| quantile_lstm | 30 | 4.98 (n=241, cov 0.70) | 4.99 (n=276, cov 0.68) | 27.78 (n=366, cov 0.70) | 22.33 (n=183, cov 0.58) |

## Paired block-bootstrap QS differences on test (A - B; negative = A better)

| h | A | B | mean diff | 95% CI | P(A better) | n |
|---|---|---|---|---|---|---|
| 1 | gbm_quantile | climatology | -13.289 | [-20.275, -7.912] | 1.000 | 1095 |
| 1 | persistence | climatology | -15.002 | [-24.197, -8.237] | 1.000 | 1095 |
| 1 | quantile_lstm | climatology | -13.981 | [-21.675, -8.033] | 1.000 | 1095 |
| 1 | climatology | persistence | 15.002 | [8.237, 24.197] | 0.000 | 1095 |
| 1 | gbm_quantile | persistence | 1.713 | [-0.071, 4.771] | 0.052 | 1095 |
| 1 | quantile_lstm | persistence | 1.021 | [0.092, 2.441] | 0.008 | 1095 |
| 1 | gbm_quantile | quantile_lstm | 0.692 | [-0.772, 2.948] | 0.271 | 1095 |
| 7 | gbm_quantile | climatology | -10.203 | [-16.040, -5.391] | 1.000 | 1089 |
| 7 | persistence | climatology | -10.076 | [-18.608, -3.617] | 1.000 | 1089 |
| 7 | quantile_lstm | climatology | -7.586 | [-11.670, -3.960] | 1.000 | 1089 |
| 7 | climatology | persistence | 10.076 | [3.617, 18.608] | 0.000 | 1089 |
| 7 | gbm_quantile | persistence | -0.127 | [-2.531, 3.537] | 0.559 | 1089 |
| 7 | quantile_lstm | persistence | 2.490 | [-0.856, 6.881] | 0.085 | 1089 |
| 7 | gbm_quantile | quantile_lstm | -2.617 | [-5.032, -0.924] | 1.000 | 1089 |
| 30 | gbm_quantile | climatology | -2.042 | [-5.112, 1.055] | 0.886 | 1066 |
| 30 | persistence | climatology | 4.221 | [-3.927, 11.450] | 0.137 | 1066 |
| 30 | quantile_lstm | climatology | -2.476 | [-4.807, -0.411] | 0.988 | 1066 |
| 30 | climatology | persistence | -4.221 | [-11.450, 3.927] | 0.863 | 1066 |
| 30 | gbm_quantile | persistence | -6.263 | [-11.824, 0.210] | 0.972 | 1066 |
| 30 | quantile_lstm | persistence | -6.697 | [-13.145, -0.071] | 0.979 | 1066 |
| 30 | gbm_quantile | quantile_lstm | 0.434 | [-1.080, 2.375] | 0.261 | 1066 |

## CV model selection (mean QS over folds and horizons; lower is better)

| model | config | mean CV QS |
|---|---|---|
| climatology | `window15` | 9.315 |
| gbm_quantile | `{"learning_rate": 0.03, "min_child_samples": 40, "n_estimators": 800, "num_leaves": 15}` | 5.760 |
| gbm_quantile | `{"learning_rate": 0.05, "min_child_samples": 40, "n_estimators": 600, "num_leaves": 7}` | 5.761 |
| gbm_quantile | `{"learning_rate": 0.05, "min_child_samples": 20, "n_estimators": 400, "num_leaves": 15}` | 5.898 |
| gbm_quantile | `{"learning_rate": 0.05, "min_child_samples": 20, "n_estimators": 400, "num_leaves": 31}` | 5.959 |
| persistence | `default` | 8.313 |
| quantile_lstm | `{"dropout": 0.1, "epochs": 60, "hidden": 64, "layers": 1, "lr": 0.002}` | 6.244 |
| quantile_lstm | `{"dropout": 0.0, "epochs": 60, "hidden": 32, "layers": 1, "lr": 0.003}` | 7.013 |
