# Forecast results (real mode)

Target: `GloFAS_v4@31.825,77.125` (MODELLED reanalysis, not observed discharge).
Dataset `2b46646ce1c0`, generated 2026-10-19T14:04:11+00:00, code `70050d62b2960564ed220071700adf95712d4b15-dirty`.

## Held-out test period (calibrated intervals)

| model | h | n | NSE | KGE | MAE | RMSE | QS | cov80 | width80 | raw cov80 |
|---|---|---|---|---|---|---|---|---|---|---|
| persistence | 1 | 1095 | 0.990 | 0.995 | 4.57 | 9.05 | 2.83 | 0.760 | 9.0 | 0.765 |
| climatology | 1 | 1095 | 0.774 | 0.625 | 26.03 | 43.55 | 18.13 | 0.763 | 50.2 | 0.791 |
| gbm_quantile | 1 | 1095 | 0.974 | 0.915 | 6.09 | 14.87 | 4.72 | 0.709 | 11.9 | 0.613 |
| quantile_lstm | 1 | 1095 | 0.985 | 0.937 | 5.56 | 11.28 | 3.92 | 0.803 | 13.3 | 0.784 |
| persistence | 7 | 1089 | 0.940 | 0.970 | 14.19 | 22.55 | 7.83 | 0.726 | 29.2 | 0.725 |
| climatology | 7 | 1089 | 0.774 | 0.625 | 26.17 | 43.68 | 18.23 | 0.763 | 50.4 | 0.790 |
| gbm_quantile | 7 | 1089 | 0.939 | 0.849 | 11.00 | 22.60 | 8.28 | 0.698 | 19.6 | 0.476 |
| quantile_lstm | 7 | 1089 | 0.908 | 0.788 | 15.51 | 27.79 | 10.71 | 0.745 | 30.0 | 0.611 |
| persistence | 30 | 1066 | 0.472 | 0.737 | 47.02 | 67.05 | 22.44 | 0.719 | 81.3 | 0.702 |
| climatology | 30 | 1066 | 0.771 | 0.624 | 26.73 | 44.16 | 18.57 | 0.759 | 50.9 | 0.785 |
| gbm_quantile | 30 | 1066 | 0.797 | 0.659 | 24.68 | 41.56 | 16.91 | 0.685 | 47.0 | 0.329 |
| quantile_lstm | 30 | 1066 | 0.833 | 0.732 | 22.10 | 37.69 | 16.13 | 0.671 | 43.6 | 0.696 |

## Seasonal QS on test (calibrated)

| model | h | winter | pre_monsoon | monsoon | post_monsoon |
|---|---|---|---|---|---|
| persistence | 1 | 0.68 (n=270, cov 0.80) | 0.89 (n=276, cov 0.65) | 6.34 (n=366, cov 0.75) | 1.92 (n=183, cov 0.88) |
| persistence | 7 | 2.09 (n=264, cov 0.71) | 2.47 (n=276, cov 0.64) | 15.99 (n=366, cov 0.75) | 7.87 (n=183, cov 0.83) |
| persistence | 30 | 9.37 (n=241, cov 0.60) | 5.43 (n=276, cov 0.55) | 38.51 (n=366, cov 0.78) | 33.18 (n=183, cov 1.00) |
| climatology | 1 | 5.52 (n=270, cov 0.80) | 3.76 (n=276, cov 0.99) | 32.95 (n=366, cov 0.62) | 28.80 (n=183, cov 0.66) |
| climatology | 7 | 5.58 (n=264, cov 0.80) | 3.79 (n=276, cov 0.99) | 32.95 (n=366, cov 0.62) | 28.80 (n=183, cov 0.66) |
| climatology | 30 | 5.89 (n=241, cov 0.78) | 3.81 (n=276, cov 0.99) | 32.94 (n=366, cov 0.62) | 28.80 (n=183, cov 0.67) |
| gbm_quantile | 1 | 0.53 (n=270, cov 0.80) | 0.94 (n=276, cov 0.63) | 12.11 (n=366, cov 0.62) | 1.84 (n=183, cov 0.87) |
| gbm_quantile | 7 | 1.02 (n=264, cov 0.86) | 2.61 (n=276, cov 0.70) | 20.13 (n=366, cov 0.47) | 3.60 (n=183, cov 0.91) |
| gbm_quantile | 30 | 3.24 (n=241, cov 0.90) | 6.25 (n=276, cov 0.69) | 34.36 (n=366, cov 0.54) | 16.09 (n=183, cov 0.69) |
| quantile_lstm | 1 | 0.59 (n=270, cov 0.93) | 1.18 (n=276, cov 0.87) | 8.45 (n=366, cov 0.69) | 3.92 (n=183, cov 0.75) |
| quantile_lstm | 7 | 1.72 (n=264, cov 0.92) | 3.08 (n=276, cov 0.92) | 22.43 (n=366, cov 0.52) | 11.77 (n=183, cov 0.69) |
| quantile_lstm | 30 | 4.77 (n=241, cov 0.77) | 4.81 (n=276, cov 0.80) | 30.24 (n=366, cov 0.54) | 19.96 (n=183, cov 0.61) |

## Paired block-bootstrap QS differences on test (A - B; negative = A better)

| h | A | B | mean diff | 95% CI | P(A better) | n |
|---|---|---|---|---|---|---|
| 1 | gbm_quantile | climatology | -13.410 | [-20.410, -7.992] | 1.000 | 1095 |
| 1 | persistence | climatology | -15.303 | [-24.719, -8.469] | 1.000 | 1095 |
| 1 | quantile_lstm | climatology | -14.209 | [-21.864, -8.218] | 1.000 | 1095 |
| 1 | climatology | persistence | 15.303 | [8.469, 24.719] | 0.000 | 1095 |
| 1 | gbm_quantile | persistence | 1.893 | [-0.064, 5.213] | 0.043 | 1095 |
| 1 | quantile_lstm | persistence | 1.093 | [0.121, 2.612] | 0.005 | 1095 |
| 1 | gbm_quantile | quantile_lstm | 0.799 | [-0.744, 3.222] | 0.245 | 1095 |
| 7 | gbm_quantile | climatology | -9.949 | [-15.626, -5.252] | 1.000 | 1089 |
| 7 | persistence | climatology | -10.397 | [-19.052, -3.835] | 1.000 | 1089 |
| 7 | quantile_lstm | climatology | -7.513 | [-11.555, -3.869] | 1.000 | 1089 |
| 7 | climatology | persistence | 10.397 | [3.835, 19.052] | 0.000 | 1089 |
| 7 | gbm_quantile | persistence | 0.449 | [-2.287, 4.431] | 0.423 | 1089 |
| 7 | quantile_lstm | persistence | 2.884 | [-0.637, 7.521] | 0.065 | 1089 |
| 7 | gbm_quantile | quantile_lstm | -2.435 | [-4.561, -0.821] | 1.000 | 1089 |
| 30 | gbm_quantile | climatology | -1.661 | [-5.216, 1.970] | 0.795 | 1066 |
| 30 | persistence | climatology | 3.869 | [-4.465, 11.273] | 0.158 | 1066 |
| 30 | quantile_lstm | climatology | -2.438 | [-5.176, 0.104] | 0.969 | 1066 |
| 30 | climatology | persistence | -3.869 | [-11.273, 4.465] | 0.842 | 1066 |
| 30 | gbm_quantile | persistence | -5.530 | [-11.339, 1.843] | 0.929 | 1066 |
| 30 | quantile_lstm | persistence | -6.307 | [-12.870, 1.027] | 0.954 | 1066 |
| 30 | gbm_quantile | quantile_lstm | 0.778 | [-0.791, 2.807] | 0.161 | 1066 |

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
