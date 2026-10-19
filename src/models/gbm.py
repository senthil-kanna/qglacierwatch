"""Gradient-boosted quantile regression (LightGBM), one booster per quantile, on log discharge.

Quantiles are equivariant under monotone transforms, so fitting log Q and exponentiating gives
valid discharge quantiles. Independent boosters can cross; predictions are sorted per row and the
pre-sort crossing rate is kept for reporting.
"""

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.features.build import horizon_matrix

QUANTILES = (0.1, 0.5, 0.9)


class GBMQuantile:
    name = "gbm_quantile"

    def __init__(self, params: dict, seed: int = 0):
        self.params = params
        self.seed = seed

    def fit(self, table: pd.DataFrame, h: int, train_idx: pd.DatetimeIndex, **_) -> "GBMQuantile":
        X, y = horizon_matrix(table.loc[train_idx], h)
        ok = y.notna()
        X, logy = X[ok], np.log(y[ok])
        self.h = h
        self.features = list(X.columns)
        self.models = []
        for tau in QUANTILES:
            m = lgb.LGBMRegressor(objective="quantile", alpha=tau, random_state=self.seed, verbose=-1, **self.params)
            m.fit(X, logy)
            self.models.append(m)
        return self

    def predict(self, table: pd.DataFrame, idx: pd.DatetimeIndex) -> np.ndarray:
        X, _ = horizon_matrix(table.loc[idx], self.h)
        raw = np.column_stack([m.predict(X[self.features]) for m in self.models])
        self.last_crossing_rate = float(np.mean((raw[:, 0] > raw[:, 1]) | (raw[:, 1] > raw[:, 2])))
        return np.exp(np.sort(raw, axis=1))

    def n_params(self) -> int:
        """Leaf values across all trees, a rough capacity measure for comparison tables."""
        total = 0
        for m in self.models:
            dump = m.booster_.dump_model()
            total += sum(t["num_leaves"] for t in dump["tree_info"])
        return total
