# Forecast results (real mode)

Target: `GloFAS_v4@31.825,77.125` (MODELLED GloFAS v4: reanalysis to 2023-08-04, forecast-derived after; not observed discharge).
Dataset `07aa2d700953`, generated 2026-10-20T07:53:38+00:00, code `75251b55ff1c66c6c91e109f48cf9924f44dff2b`.

## Held-out test period (calibrated intervals)

| model | h | n | NSE | KGE | MAE | RMSE | QS | cov80 | width80 | raw cov80 |
|---|---|---|---|---|---|---|---|---|---|---|
| persistence | 1 | 272 | 0.993 | 0.991 | 3.02 | 5.37 | 1.87 | 0.860 | 9.6 | 0.805 |
| climatology | 1 | 272 | 0.916 | 0.819 | 13.68 | 18.75 | 9.27 | 0.871 | 65.9 | 0.864 |
| gbm_quantile | 1 | 272 | 0.994 | 0.978 | 2.36 | 4.90 | 1.89 | 0.938 | 16.1 | 0.757 |
| quantile_lstm | 1 | 272 | 0.995 | 0.985 | 2.80 | 4.56 | 2.01 | 0.864 | 15.1 | 0.893 |
| persistence | 7 | 266 | 0.947 | 0.952 | 9.27 | 15.07 | 5.32 | 0.827 | 30.4 | 0.703 |
| climatology | 7 | 266 | 0.918 | 0.817 | 13.55 | 18.74 | 9.14 | 0.895 | 67.0 | 0.883 |
| gbm_quantile | 7 | 266 | 0.980 | 0.977 | 5.82 | 9.18 | 4.27 | 0.887 | 32.9 | 0.560 |
| quantile_lstm | 7 | 266 | 0.975 | 0.907 | 6.58 | 10.34 | 4.59 | 0.820 | 33.1 | 0.774 |
| persistence | 30 | 243 | 0.521 | 0.643 | 29.86 | 46.92 | 15.59 | 0.811 | 72.6 | 0.646 |
| climatology | 30 | 243 | 0.919 | 0.812 | 13.85 | 19.30 | 9.55 | 0.955 | 73.4 | 0.922 |
| gbm_quantile | 30 | 243 | 0.962 | 0.928 | 9.56 | 13.14 | 8.32 | 0.955 | 72.7 | 0.453 |
| quantile_lstm | 30 | 243 | 0.960 | 0.917 | 10.14 | 13.61 | 8.29 | 0.947 | 73.0 | 0.609 |

## Seasonal QS on test (calibrated)

| model | h | winter | pre_monsoon | monsoon | post_monsoon |
|---|---|---|---|---|---|
| persistence | 1 | 0.55 (n=58, cov 0.86) | 0.54 (n=92, cov 0.89) | 3.49 (n=122, cov 0.84) | nan (n=0, cov nan) |
| persistence | 7 | 2.04 (n=52, cov 0.60) | 1.38 (n=92, cov 0.87) | 9.68 (n=122, cov 0.89) | nan (n=0, cov nan) |
| persistence | 30 | 8.39 (n=29, cov 0.03) | 4.44 (n=92, cov 1.00) | 25.72 (n=122, cov 0.85) | nan (n=0, cov nan) |
| climatology | 1 | 4.99 (n=58, cov 0.60) | 2.88 (n=92, cov 0.93) | 16.12 (n=122, cov 0.95) | nan (n=0, cov nan) |
| climatology | 7 | 3.85 (n=52, cov 0.69) | 2.88 (n=92, cov 0.93) | 16.12 (n=122, cov 0.95) | nan (n=0, cov nan) |
| climatology | 30 | 3.03 (n=29, cov 1.00) | 2.88 (n=92, cov 0.95) | 16.12 (n=122, cov 0.95) | nan (n=0, cov nan) |
| gbm_quantile | 1 | 0.28 (n=58, cov 0.95) | 0.52 (n=92, cov 0.85) | 3.69 (n=122, cov 1.00) | nan (n=0, cov nan) |
| gbm_quantile | 7 | 0.82 (n=52, cov 0.83) | 1.56 (n=92, cov 0.79) | 7.78 (n=122, cov 0.98) | nan (n=0, cov nan) |
| gbm_quantile | 30 | 2.24 (n=29, cov 1.00) | 4.77 (n=92, cov 1.00) | 12.44 (n=122, cov 0.91) | nan (n=0, cov nan) |
| quantile_lstm | 1 | 0.61 (n=58, cov 0.66) | 0.65 (n=92, cov 0.91) | 3.69 (n=122, cov 0.93) | nan (n=0, cov nan) |
| quantile_lstm | 7 | 1.60 (n=52, cov 0.77) | 1.44 (n=92, cov 0.68) | 8.24 (n=122, cov 0.94) | nan (n=0, cov nan) |
| quantile_lstm | 30 | 1.84 (n=29, cov 0.93) | 4.37 (n=92, cov 1.00) | 12.79 (n=122, cov 0.91) | nan (n=0, cov nan) |

## Paired block-bootstrap QS differences on test (A - B; negative = A better)

| h | A | B | mean diff | 95% CI | P(A better) | n |
|---|---|---|---|---|---|---|
| 1 | gbm_quantile | climatology | -7.378 | [-11.126, -3.653] | 1.000 | 272 |
| 1 | persistence | climatology | -7.403 | [-11.374, -3.604] | 1.000 | 272 |
| 1 | quantile_lstm | climatology | -7.262 | [-11.241, -3.409] | 1.000 | 272 |
| 1 | climatology | persistence | 7.403 | [3.604, 11.374] | 0.000 | 272 |
| 1 | gbm_quantile | persistence | 0.025 | [-0.117, 0.271] | 0.322 | 272 |
| 1 | quantile_lstm | persistence | 0.141 | [-0.143, 0.428] | 0.158 | 272 |
| 1 | gbm_quantile | quantile_lstm | -0.116 | [-0.370, 0.248] | 0.733 | 272 |
| 7 | gbm_quantile | climatology | -4.876 | [-7.459, -2.056] | 1.000 | 266 |
| 7 | persistence | climatology | -3.826 | [-6.089, -1.965] | 1.000 | 266 |
| 7 | quantile_lstm | climatology | -4.552 | [-7.736, -1.803] | 1.000 | 266 |
| 7 | climatology | persistence | 3.826 | [1.965, 6.089] | 0.000 | 266 |
| 7 | gbm_quantile | persistence | -1.049 | [-1.879, 0.050] | 0.963 | 266 |
| 7 | quantile_lstm | persistence | -0.726 | [-2.141, 0.584] | 0.824 | 266 |
| 7 | gbm_quantile | quantile_lstm | -0.323 | [-0.896, 0.570] | 0.577 | 266 |
| 30 | gbm_quantile | climatology | -1.229 | [-3.844, 0.881] | 0.871 | 243 |
| 30 | persistence | climatology | 6.044 | [0.336, 12.268] | 0.014 | 243 |
| 30 | quantile_lstm | climatology | -1.254 | [-5.551, 0.959] | 0.898 | 243 |
| 30 | climatology | persistence | -6.044 | [-12.268, -0.336] | 0.986 | 243 |
| 30 | gbm_quantile | persistence | -7.273 | [-15.605, -0.334] | 0.984 | 243 |
| 30 | quantile_lstm | persistence | -7.298 | [-16.111, -0.833] | 0.998 | 243 |
| 30 | gbm_quantile | quantile_lstm | 0.025 | [-0.904, 2.810] | 0.251 | 243 |

## CV model selection (mean QS over folds and horizons; lower is better)

| model | config | mean CV QS |
|---|---|---|
| climatology | `window15` | 9.646 |
| gbm_quantile | `{"learning_rate": 0.05, "min_child_samples": 40, "n_estimators": 600, "num_leaves": 7}` | 6.410 |
| gbm_quantile | `{"learning_rate": 0.03, "min_child_samples": 40, "n_estimators": 800, "num_leaves": 15}` | 6.449 |
| gbm_quantile | `{"learning_rate": 0.05, "min_child_samples": 20, "n_estimators": 400, "num_leaves": 15}` | 6.656 |
| gbm_quantile | `{"learning_rate": 0.05, "min_child_samples": 20, "n_estimators": 400, "num_leaves": 31}` | 6.724 |
| persistence | `default` | 8.812 |
| quantile_lstm | `{"dropout": 0.1, "epochs": 60, "hidden": 64, "layers": 1, "lr": 0.002}` | 6.474 |
| quantile_lstm | `{"dropout": 0.0, "epochs": 60, "hidden": 32, "layers": 1, "lr": 0.003}` | 7.493 |
