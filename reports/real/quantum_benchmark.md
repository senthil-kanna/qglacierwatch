# Quantum-classical benchmark (real mode, h=7 days)

> Noiseless simulation on a classical CPU. Results bear on accuracy of this model class for this task, not on quantum advantage.

Inputs: 4 PCA components (83.4% of training variance). Seeds [101, 202, 303, 404, 505]; lr grid [0.01, 0.05]; up to 40 epochs. Simulator: default.qubit (PennyLane state-vector, noiseless), PennyLane 0.45.1.

| model | params (circuit) | test QS mean +/- sd | 95% CI | coverage | NSE | train s (all lr) | circuit evals (train) | param-shift equiv. |
|---|---|---|---|---|---|---|---|---|
| vqc | 39 (24) | 28.884 +/- 3.202 | [24.907, 32.860] | 0.725 | 0.400 | 14.0 | 40378 | 1978502 |
| vqc_noent | 39 (24) | 20.422 +/- 0.480 | [19.825, 21.018] | 0.799 | 0.607 | 12.0 | 43322 | 2122768 |
| vqc_1layer | 27 (12) | 38.325 +/- 1.882 | [35.989, 40.661] | 0.765 | -0.038 | 6.8 | 32386 | 809655 |
| vqc_6q | 57 (36) | 29.100 +/- 1.147 | [27.677, 30.524] | 0.734 | 0.406 | 27.2 | 58043 | 4237124 |
| linear | 15 (0) | 10.139 +/- 0.287 | [9.783, 10.496] | 0.780 | 0.908 | 0.8 | 0 | 0 |
| mlp_matched | 43 (0) | 11.722 +/- 0.383 | [11.247, 12.198] | 0.748 | 0.899 | 0.7 | 0 | 0 |
| mlp_large | 259 (0) | 11.146 +/- 0.882 | [10.051, 12.242] | 0.741 | 0.913 | 0.7 | 0 | 0 |

## Paired comparisons (VQC - other; negative = VQC better)

| other | mean diff | t 95% CI (seeds) | paired t p | Wilcoxon p | block-bootstrap CI (seed-avg) |
|---|---|---|---|---|---|
| vqc_noent | 8.462 | [4.795, 12.129] | 0.003 | 0.0625 | [4.955, 12.994] |
| vqc_1layer | -9.441 | [-14.430, -4.453] | 0.006 | 0.0625 | [-12.632, -6.567] |
| vqc_6q | -0.217 | [-4.179, 3.745] | 0.887 | 0.8125 | [-2.976, 3.197] |
| linear | 18.744 | [14.572, 22.917] | 0.000 | 0.0625 | [8.854, 31.520] |
| mlp_matched | 17.161 | [12.930, 21.393] | 0.000 | 0.0625 | [9.092, 27.362] |
| mlp_large | 17.737 | [12.770, 22.704] | 0.001 | 0.0625 | [9.215, 28.558] |

Finite-shot re-evaluation of VQC (seed 101, 1000 shots): test QS 27.396, coverage 0.732 (0.1 s).

Reference (full feature set, main experiment, same test period): persistence 7.829, climatology 18.227, gbm_quantile 8.278, quantile_lstm 10.713

Note: with 5 seeds the smallest attainable two-sided exact Wilcoxon p-value is 0.0625.
