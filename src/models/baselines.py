"""Reference forecasts every learned model must beat.

Persistence: P50 is the last available discharge; P10/P90 come from training-period quantiles of
log(Q[t+h] / Q_last) for the same target month, so the spread is seasonal but uses no future data.

Climatology: quantiles of training-period discharge within +/- window days of the target
day-of-year. Uses no information about the current state of the basin.
"""

import numpy as np
import pandas as pd

QUANTILES = (0.1, 0.5, 0.9)


class Persistence:
    name = "persistence"

    def fit(self, table: pd.DataFrame, h: int, train_idx: pd.DatetimeIndex, **_) -> "Persistence":
        rows = table.loc[train_idx]
        ratio = np.log(rows[f"y_h{h}"] / rows["q0"])
        month = (train_idx + pd.Timedelta(days=h)).month
        q = ratio.groupby(month).quantile([QUANTILES[0], QUANTILES[2]]).unstack()
        overall = ratio.quantile([QUANTILES[0], QUANTILES[2]])
        self.offsets = {m: (q.loc[m].iloc[0], q.loc[m].iloc[1]) if m in q.index else tuple(overall) for m in range(1, 13)}
        self.h = h
        return self

    def predict(self, table: pd.DataFrame, idx: pd.DatetimeIndex) -> np.ndarray:
        q0 = table.loc[idx, "q0"].to_numpy()
        month = (idx + pd.Timedelta(days=self.h)).month
        # In recession months even the 90th-percentile log ratio can be negative; P50 stays the last
        # observation (pure persistence), so the band is widened to contain it.
        lo = np.minimum([self.offsets[m][0] for m in month], 0.0)
        hi = np.maximum([self.offsets[m][1] for m in month], 0.0)
        return np.column_stack([q0 * np.exp(lo), q0, q0 * np.exp(hi)])


class Climatology:
    name = "climatology"

    def __init__(self, window: int = 15):
        self.window = window

    def fit(self, table: pd.DataFrame, h: int, train_idx: pd.DatetimeIndex, **_) -> "Climatology":
        obs = table.loc[train_idx, f"y_h{h}"]
        obs.index = train_idx + pd.Timedelta(days=h)  # verification dates, all inside training period
        obs = obs.dropna()
        doy = obs.index.dayofyear.to_numpy()
        vals = obs.to_numpy()
        self.table = np.zeros((367, 3))
        for d in range(1, 367):
            dist = np.abs(doy - d)
            dist = np.minimum(dist, 366 - dist)  # circular day-of-year distance
            self.table[d] = np.quantile(vals[dist <= self.window], QUANTILES)
        self.h = h
        return self

    def predict(self, table: pd.DataFrame, idx: pd.DatetimeIndex) -> np.ndarray:
        doy = (idx + pd.Timedelta(days=self.h)).dayofyear.to_numpy()
        return self.table[doy]
