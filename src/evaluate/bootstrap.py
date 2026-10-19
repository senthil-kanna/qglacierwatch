"""Paired moving-block bootstrap for score differences between two forecasts on the same dates.

Daily forecast errors are autocorrelated, so resampling single days would understate the
uncertainty. Blocks of consecutive days keep that dependence.
"""

import numpy as np


def block_bootstrap_diff(loss_a, loss_b, block: int = 30, n: int = 1000, ci: float = 0.95, seed: int = 0) -> dict:
    """CI for mean(loss_a - loss_b). Negative means A has lower loss (better)."""
    d = np.asarray(loss_a, float) - np.asarray(loss_b, float)
    d = d[np.isfinite(d)]
    T = len(d)
    if T == 0:
        return {"mean_diff": float("nan"), "lo": float("nan"), "hi": float("nan"), "p_a_better": float("nan"), "n": 0}
    block = max(1, min(block, T))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(T / block))
    starts = rng.integers(0, T - block + 1, size=(n, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n, -1)[:, :T]
    means = d[idx].mean(axis=1)
    alpha = (1 - ci) / 2
    return {
        "mean_diff": float(d.mean()),
        "lo": float(np.quantile(means, alpha)),
        "hi": float(np.quantile(means, 1 - alpha)),
        "p_a_better": float(np.mean(means < 0)),
        "n": int(T),
        "block_days": block,
        "resamples": n,
    }
