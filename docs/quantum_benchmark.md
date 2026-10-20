# Quantum-classical benchmark: design and findings

Results: `reports/real/quantum_benchmark.md` (run 2026-10-19). Regenerate with
`python -m src.quantum.benchmark --mode real` (5.2 minutes of total training time on a 16-thread laptop CPU).

## Question

Can a variational quantum circuit (VQC), simulated exactly, match capacity-matched classical
models at predicting 7-day discharge quantiles, under identical data, features, targets, tuning
budget and calibration? This is a feasibility and accuracy comparison. **A classical simulation
cannot demonstrate quantum advantage**; every VQC output was computed by a classical CPU in a
fraction of a second.

## Set-up (identical for every model)

| item | value |
|---|---|
| task | P10/P50/P90 of discharge at t+7 days, standardised log target |
| inputs | 4 PCA components of the 34 standard features (PCA, scaling and imputation fitted on training rows; 83.4% of training variance) |
| splits | train 2015-2020 (inner hold-out: last 365 days for early stopping and lr choice), calibration 2021-2022 (CQR), test 2023-2025 |
| optimiser | Adam, batch 64, up to 40 epochs, patience 6 |
| tuning budget | lr in {0.01, 0.05} for every model, chosen on the inner hold-out |
| head | shared monotone quantile head (linear + softplus increments) |
| seeds | 101, 202, 303, 404, 505 |
| uncertainty | native pinball-loss quantiles, then the same CQR conformal step as the main models |

## Circuit

Per layer: RY(pi * x_i) angle encoding on each qubit (data re-uploading), a general Rot(a, b, c) per
qubit, and a CNOT ring (if entangled). Readout: <Z_i> on every qubit (analytic expectations;
PennyLane `default.qubit`, backprop). Main VQC: 4 qubits, 2 layers, 24 circuit parameters + 15 head
parameters = 39. Finite-shot check: trained VQC re-evaluated with 1,000 shots.

## Findings (test QS, m3/s, mean +/- sd over 5 seeds; lower is better)

| model | params | QS |
|---|---|---|
| VQC (4 qubits, 2 layers, CNOT ring) | 39 | 28.88 +/- 3.20 |
| VQC without entanglement | 39 | 20.42 +/- 0.48 |
| VQC, 1 layer (no re-uploading) | 27 | 38.33 +/- 1.88 |
| VQC, 6 qubits / 6 PCA inputs | 57 | 29.10 +/- 1.15 |
| linear on the same 4 inputs | 15 | 10.14 +/- 0.29 |
| MLP, parameter-matched | 43 | 11.72 +/- 0.38 |
| MLP, 32 hidden | 259 | 11.15 +/- 0.88 |
| (context) climatology / persistence / GBM, full features | - | 18.23 / 7.83 / 8.28 |

- The VQC is worse than every classical model on the same inputs, including the 15-parameter linear model (paired difference +18.7, seed-paired t 95% CI [14.6, 22.9]; block-bootstrap CI on seed-averaged forecasts [8.9, 31.5]). It is also worse than climatology.
- Removing entanglement improved the VQC (paired difference +8.5, CI [4.8, 12.1]); data re-uploading helped (removing it: -9.4, CI [-14.4, -4.5] in favour of 2 layers). More qubits did not help.
- 1,000-shot inference gave QS 27.4 for seed 101, close to the analytic result.
- With 5 seeds the smallest exact Wilcoxon p-value is 0.0625, so Wilcoxon tests cannot reach 0.05; t-based intervals are reported alongside.

## Interpretation and limits

The VQC maps inputs through bounded, periodic features (<Z> in [-1, 1] of trigonometric functions of
the inputs), while discharge in log space is close to linear in the leading PCA components. The
linear model's advantage is consistent with that. The comparison is fixed-budget: a longer schedule, other
encodings (e.g. trainable input scaling) or a classical skip connection might narrow the gap, but
the latter would make the classical part do the work. Training cost: about 40k circuit forward
evaluations per run on the simulator; on hardware with parameter-shift gradients the same training
would need about 2 million circuit executions (forward evals x (1 + 2 x 24)), before shot repetitions.
