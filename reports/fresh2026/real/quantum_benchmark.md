# Quantum-classical benchmark (real mode, h=7 days)

> Noiseless simulation on a classical CPU. Results bear on accuracy of this model class for this task, not on quantum advantage.

Inputs: 4 PCA components (83.3% of training variance). Seeds [101, 202, 303, 404, 505]; lr grid [0.01, 0.05]; up to 40 epochs. Simulator: default.qubit (PennyLane state-vector, noiseless), PennyLane 0.45.1.

| model | params (circuit) | test QS mean +/- sd | 95% CI | coverage | NSE | train s (all lr) | circuit evals (train) | param-shift equiv. |
|---|---|---|---|---|---|---|---|---|
| vqc | 39 (24) | 15.906 +/- 2.998 | [12.183, 19.629] | 0.910 | 0.686 | 21.6 | 88904 | 4356316 |
| vqc_noent | 39 (24) | 10.381 +/- 0.513 | [9.744, 11.017] | 0.903 | 0.872 | 14.7 | 47330 | 2319190 |
| vqc_1layer | 27 (12) | 27.653 +/- 2.507 | [24.540, 30.766] | 0.768 | 0.209 | 12.4 | 58204 | 1455090 |
| vqc_6q | 57 (36) | 15.138 +/- 2.028 | [12.620, 17.657] | 0.887 | 0.697 | 78.1 | 81869 | 5976422 |
| linear | 15 (0) | 6.464 +/- 0.036 | [6.420, 6.508] | 0.890 | 0.952 | 1.0 | 0 | 0 |
| mlp_matched | 43 (0) | 7.159 +/- 0.742 | [6.237, 8.081] | 0.859 | 0.936 | 1.1 | 0 | 0 |
| mlp_large | 259 (0) | 6.581 +/- 0.231 | [6.294, 6.868] | 0.876 | 0.951 | 1.6 | 0 | 0 |

## Paired comparisons (VQC - other; negative = VQC better)

| other | mean diff | t 95% CI (seeds) | paired t p | Wilcoxon p | block-bootstrap CI (seed-avg) |
|---|---|---|---|---|---|
| vqc_noent | 5.526 | [1.861, 9.190] | 0.014 | 0.0625 | [2.231, 9.555] |
| vqc_1layer | -11.746 | [-18.042, -5.451] | 0.007 | 0.0625 | [-18.532, -6.658] |
| vqc_6q | 0.768 | [-5.085, 6.620] | 0.734 | 0.4375 | [-1.760, 2.807] |
| linear | 9.442 | [5.716, 13.168] | 0.002 | 0.0625 | [3.862, 16.007] |
| mlp_matched | 8.747 | [4.443, 13.052] | 0.005 | 0.0625 | [3.762, 14.571] |
| mlp_large | 9.325 | [5.691, 12.959] | 0.002 | 0.0625 | [3.706, 15.830] |

Finite-shot re-evaluation of VQC (seed 101, 1000 shots): test QS 20.041, coverage 0.872 (0.1 s).

Reference (full feature set, main experiment, same test period): persistence 5.317, climatology 9.143, gbm_quantile 4.268, quantile_lstm 4.591

Note: with 5 seeds the smallest attainable two-sided exact Wilcoxon p-value is 0.0625.
