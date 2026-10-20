"""Conformalized quantile regression (Romano et al., 2019) for the P10-P90 interval.

Conformity scores E = max(log q10 - log y, log y - log q90) are computed on the calibration
period only. The interval is widened (or narrowed, if E's quantile is negative) by the
finite-sample (1-alpha)(1+1/n) quantile of E, in log space so the adjustment is multiplicative
and bounds stay positive. P50 is unchanged.

With `seasons` (month -> season map), offsets are fitted per season of the target date
(Mondrian CQR), so a wide monsoon offset no longer has to share one value with calm winter days.
A season with fewer than `min_group` calibration samples uses the pooled offset.

Caveat: conformal guarantees assume exchangeability, which daily discharge violates. Coverage is
therefore checked empirically on the held-out test period, never assumed.
"""

import numpy as np
import pandas as pd


def _offset(e: np.ndarray, alpha: float) -> float:
    level = min(1.0, (1 - alpha) * (1 + 1 / len(e)))
    return float(np.quantile(e, level, method="higher"))


class CQR:
    def __init__(self, target_coverage: float = 0.8, seasons: dict | None = None, min_group: int = 60):
        self.alpha = 1 - target_coverage
        self.month_to_season = {m: s for s, months in (seasons or {}).items() for m in months}
        self.min_group = min_group
        self.q_hat_by_season: dict[str, float] = {}

    def _groups(self, dates, n: int) -> np.ndarray | None:
        if not getattr(self, "month_to_season", None) or dates is None:
            return None
        months = pd.DatetimeIndex(dates).month
        if len(months) != n:
            raise ValueError("dates must align with predictions")
        return np.array([self.month_to_season.get(m) for m in months], dtype=object)

    def fit(self, y, qpred, dates=None) -> "CQR":
        y = np.asarray(y, float)
        qpred = np.asarray(qpred, float)
        ok = np.isfinite(y) & np.all(np.isfinite(qpred), axis=1)
        ly, lq = np.log(y[ok]), np.log(qpred[ok])
        e = np.maximum(lq[:, 0] - ly, ly - lq[:, 2])
        n = len(e)
        if n == 0:
            raise ValueError("CQR calibration set is empty")
        self.q_hat = _offset(e, self.alpha)
        self.n = n
        groups = self._groups(dates, len(y))
        self.q_hat_by_season = {}
        if groups is not None:
            g = groups[ok]
            for s in set(self.month_to_season.values()):
                es = e[g == s]
                if len(es) >= self.min_group:
                    self.q_hat_by_season[s] = _offset(es, self.alpha)
        return self

    def apply(self, qpred, dates=None) -> np.ndarray:
        q = np.asarray(qpred, float).copy()
        off = np.full(len(q), self.q_hat)
        groups = self._groups(dates, len(q))
        by_season = getattr(self, "q_hat_by_season", {})
        if groups is not None and by_season:
            off = np.array([by_season.get(s, self.q_hat) for s in groups])
        q[:, 0] = q[:, 0] * np.exp(-off)
        q[:, 2] = q[:, 2] * np.exp(off)
        # A negative offset can narrow the band past the median; keep P10 <= P50 <= P90.
        q[:, 0] = np.minimum(q[:, 0], q[:, 1])
        q[:, 2] = np.maximum(q[:, 2], q[:, 1])
        return q


def make_cqr(cfg: dict) -> CQR:
    """CQR as configured in configs/forecast.yaml (pooled, or per season when by_season is set)."""
    c = cfg["calibration"]
    seasons = cfg["seasons"] if c.get("by_season") else None
    return CQR(c["target_coverage"], seasons, c.get("min_season_samples", 60))
