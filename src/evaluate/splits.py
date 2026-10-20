"""Time-ordered splits with a horizon embargo.

A training sample issued on t has its target on t+h. If t+h falls inside a later period, that
sample would leak the later period's discharge into training, so it is dropped (embargo).
"""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Period:
    start: pd.Timestamp
    end: pd.Timestamp

    @classmethod
    def of(cls, bounds) -> "Period":
        return cls(pd.Timestamp(bounds[0]), pd.Timestamp(bounds[1]))


def issue_mask(index: pd.DatetimeIndex, period: Period, h: int, embargo: bool = True) -> pd.Series:
    """Issue dates within the period whose target date also lies within it (if embargo)."""
    m = (index >= period.start) & (index <= period.end)
    if embargo:
        m &= (index + pd.Timedelta(days=h)) <= period.end
    return pd.Series(m, index=index)


def main_splits(cfg: dict) -> dict[str, Period]:
    return {k: Period.of(v) for k, v in cfg["splits"].items()}


def cv_folds(cfg: dict) -> list[tuple[Period, Period]]:
    """Expanding-window folds: train from the first train date to the end of year Y-1, validate on Y."""
    start = pd.Timestamp(cfg["splits"]["train"][0])
    folds = []
    for y in cfg["cv_validation_years"]:
        folds.append((Period(start, pd.Timestamp(f"{y - 1}-12-31")), Period(pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31"))))
    return folds


def assert_ordered(*periods: Period) -> None:
    for a, b in zip(periods, periods[1:], strict=False):
        if not a.end < b.start:
            raise ValueError(f"Periods overlap or are out of order: {a} then {b}")
