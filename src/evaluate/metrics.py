"""Deterministic and probabilistic forecast metrics.

Conventions (also in docs/protocol.md):
- Deterministic scores (NSE, KGE, MAE, RMSE) use the P50 forecast.
- KGE follows Gupta et al. (2009): 1 - sqrt((r-1)^2 + (alpha-1)^2 + (beta-1)^2), alpha = sd_sim/sd_obs,
  beta = mean_sim/mean_obs.
- QS is the mean over tau in {0.1, 0.5, 0.9} of 2 * pinball_tau. CRPS = integral of 2*pinball over tau,
  so QS is a 3-point quadrature approximation of CRPS in m3/s (coarse; documented as such).
- Coverage is the share of observations inside [P10, P90]; nominal 0.80.
- Any score that is mathematically undefined (zero variance, empty sample) is returned as NaN,
  never silently set to 0.
"""

import numpy as np
import pandas as pd

QUANTILES = (0.1, 0.5, 0.9)


def _clean(obs, sim):
    obs, sim = np.asarray(obs, float), np.asarray(sim, float)
    ok = np.isfinite(obs) & np.isfinite(sim)
    return obs[ok], sim[ok]


def nse(obs, sim) -> float:
    o, s = _clean(obs, sim)
    if len(o) < 2 or np.var(o) == 0:
        return float("nan")
    return float(1 - np.sum((s - o) ** 2) / np.sum((o - o.mean()) ** 2))


def kge(obs, sim) -> float:
    o, s = _clean(obs, sim)
    if len(o) < 2 or o.std() == 0 or s.std() == 0 or o.mean() == 0:
        return float("nan")
    r = np.corrcoef(o, s)[0, 1]
    alpha = s.std() / o.std()
    beta = s.mean() / o.mean()
    return float(1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))


def mae(obs, sim) -> float:
    o, s = _clean(obs, sim)
    return float(np.mean(np.abs(s - o))) if len(o) else float("nan")


def rmse(obs, sim) -> float:
    o, s = _clean(obs, sim)
    return float(np.sqrt(np.mean((s - o) ** 2))) if len(o) else float("nan")


def pinball(obs, q, tau: float) -> np.ndarray:
    d = np.asarray(obs, float) - np.asarray(q, float)
    return np.maximum(tau * d, (tau - 1) * d)


def quantile_score(obs, qpred: np.ndarray, quantiles=QUANTILES) -> np.ndarray:
    """Per-sample QS (CRPS approximation). qpred has shape (n, len(quantiles))."""
    qpred = np.asarray(qpred, float)
    return np.mean([2 * pinball(obs, qpred[:, i], t) for i, t in enumerate(quantiles)], axis=0)


def coverage(obs, lo, hi) -> float:
    o = np.asarray(obs, float)
    ok = np.isfinite(o)
    if not ok.any():
        return float("nan")
    return float(np.mean((o[ok] >= np.asarray(lo)[ok]) & (o[ok] <= np.asarray(hi)[ok])))


def score_all(obs, qpred: np.ndarray) -> dict:
    obs = np.asarray(obs, float)
    qpred = np.asarray(qpred, float)
    ok = np.isfinite(obs) & np.all(np.isfinite(qpred), axis=1)
    o, qp = obs[ok], qpred[ok]
    if len(o) == 0:
        keys = ["nse", "kge", "mae", "rmse", "qs", "coverage_80", "width_80", "crossing_rate"]
        return {"n": 0, **{k: float("nan") for k in keys}}
    return {
        "n": int(len(o)),
        "nse": nse(o, qp[:, 1]),
        "kge": kge(o, qp[:, 1]),
        "mae": mae(o, qp[:, 1]),
        "rmse": rmse(o, qp[:, 1]),
        "qs": float(np.mean(quantile_score(o, qp))),
        "coverage_80": coverage(o, qp[:, 0], qp[:, 2]),
        "width_80": float(np.mean(qp[:, 2] - qp[:, 0])),
        "crossing_rate": float(np.mean((qp[:, 0] > qp[:, 1]) | (qp[:, 1] > qp[:, 2]))),
    }


def season_of(index: pd.DatetimeIndex, seasons: dict[str, list[int]]) -> np.ndarray:
    lookup = {m: s for s, months in seasons.items() for m in months}
    return np.array([lookup[m] for m in index.month])


def score_by_season(target_dates: pd.DatetimeIndex, obs, qpred, seasons: dict) -> dict:
    """Seasonal breakdown keyed on the target (verification) date."""
    labels = season_of(target_dates, seasons)
    out = {}
    for s in seasons:
        m = labels == s
        out[s] = score_all(np.asarray(obs)[m], np.asarray(qpred)[m])
    return out
