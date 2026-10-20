"""Conformalized quantile regression (Romano et al., 2019) for the P10-P90 interval.

Conformity scores E = max(log q10 - log y, log y - log q90) are computed on the calibration
period only. The interval is widened (or narrowed, if E's quantile is negative) by the
finite-sample (1-alpha)(1+1/n) quantile of E, in log space so the adjustment is multiplicative
and bounds stay positive. P50 is unchanged.

Caveat: conformal guarantees assume exchangeability, which daily discharge violates. Coverage is
therefore checked empirically on the held-out test period, never assumed.
"""

import numpy as np


class CQR:
    def __init__(self, target_coverage: float = 0.8):
        self.alpha = 1 - target_coverage

    def fit(self, y, qpred) -> "CQR":
        y = np.asarray(y, float)
        qpred = np.asarray(qpred, float)
        ok = np.isfinite(y) & np.all(np.isfinite(qpred), axis=1)
        ly, lq = np.log(y[ok]), np.log(qpred[ok])
        e = np.maximum(lq[:, 0] - ly, ly - lq[:, 2])
        n = len(e)
        if n == 0:
            raise ValueError("CQR calibration set is empty")
        level = min(1.0, (1 - self.alpha) * (1 + 1 / n))
        self.q_hat = float(np.quantile(e, level, method="higher"))
        self.n = n
        return self

    def apply(self, qpred) -> np.ndarray:
        q = np.asarray(qpred, float).copy()
        q[:, 0] = q[:, 0] * np.exp(-self.q_hat)
        q[:, 2] = q[:, 2] * np.exp(self.q_hat)
        # A negative q_hat can narrow the band past the median; keep P10 <= P50 <= P90.
        q[:, 0] = np.minimum(q[:, 0], q[:, 1])
        q[:, 2] = np.maximum(q[:, 2], q[:, 1])
        return q
