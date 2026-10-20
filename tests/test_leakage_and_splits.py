import numpy as np
import pandas as pd
import pytest

from src.evaluate.splits import Period, assert_ordered, cv_folds, issue_mask
from src.features.build import FEATURE_COLS, SEQ_COLS, build_features, horizon_matrix


def test_features_ignore_future_values(daily, cfg):
    """Corrupting every input after a cut date must not change any feature on or before it."""
    cut = pd.Timestamp("2019-06-15")
    base = build_features(daily, cfg["availability_lag_days"], cfg["horizons"])
    corrupted = daily.copy()
    after = corrupted.index > cut
    corrupted.loc[after] = corrupted.loc[after] * 3.0 + 7.0
    pert = build_features(corrupted, cfg["availability_lag_days"], cfg["horizons"])
    cols = FEATURE_COLS + SEQ_COLS
    pd.testing.assert_frame_equal(base.loc[:cut, cols], pert.loc[:cut, cols])


def test_availability_lag_is_applied(daily, cfg):
    lags = cfg["availability_lag_days"]
    f = build_features(daily, lags, cfg["horizons"])
    t = pd.Timestamp("2018-03-10")
    assert f.loc[t, "q0"] == pytest.approx(daily.loc[t - pd.Timedelta(days=lags["discharge"]), "discharge_m3s"])
    assert f.loc[t, "seq_t"] == pytest.approx(daily.loc[t - pd.Timedelta(days=lags["era5"]), "temperature_2m"])


def test_targets_are_future_discharge(daily, cfg):
    f = build_features(daily, cfg["availability_lag_days"], cfg["horizons"])
    t = pd.Timestamp("2018-03-10")
    for h in cfg["horizons"]:
        assert f.loc[t, f"y_h{h}"] == pytest.approx(daily.loc[t + pd.Timedelta(days=h), "discharge_m3s"])
    assert not any(c.startswith("y_") for c in horizon_matrix(f, 7)[0].columns)


def test_snow_gap_fill_is_causal(daily, cfg):
    f = build_features(daily, cfg["availability_lag_days"], cfg["horizons"])
    shifted = daily["snow_frac_valid"].shift(cfg["availability_lag_days"]["modis"])
    missing = shifted.isna() & shifted.ffill().notna()
    d = missing[missing].index[10]
    prev_valid = shifted.loc[:d].dropna().iloc[-1]
    assert f.loc[d, "snow_frac"] == pytest.approx(prev_valid)
    assert f.loc[d, "snow_age"] >= 1


def test_embargo_drops_samples_whose_target_crosses_boundary():
    idx = pd.date_range("2020-12-01", "2021-01-31")
    p = Period(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"))
    m = issue_mask(idx, p, h=7)
    kept = idx[m.to_numpy()]
    assert kept.max() == pd.Timestamp("2020-12-24")
    assert ((kept + pd.Timedelta(days=7)) <= p.end).all()


def test_cv_folds_are_expanding_and_ordered(cfg):
    folds = cv_folds(cfg)
    for tr, va in folds:
        assert tr.end < va.start
        assert tr.start == pd.Timestamp(cfg["splits"]["train"][0])
    ends = [tr.end for tr, _ in folds]
    assert ends == sorted(ends)
    assert folds[-1][1].end < pd.Timestamp(cfg["splits"]["test"][0])  # CV never touches test


def test_main_periods_do_not_overlap(cfg):
    s = {k: Period.of(v) for k, v in cfg["splits"].items()}
    assert_ordered(s["train"], s["calibration"], s["test"])
    with pytest.raises(ValueError):
        assert_ordered(s["test"], s["train"])


def test_missing_discharge_propagates_as_nan_not_zero(daily, cfg):
    d = daily.copy()
    d.loc["2018-05-01":"2018-05-03", "discharge_m3s"] = np.nan
    f = build_features(d, cfg["availability_lag_days"], cfg["horizons"])
    assert np.isnan(f.loc["2018-05-02", "q0"])
    assert f.loc["2018-05-02", "flag_q_missing"] == 1
    assert np.isnan(f.loc["2018-04-30", "y_h1"])
