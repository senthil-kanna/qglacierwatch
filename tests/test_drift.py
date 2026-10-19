import numpy as np
import pandas as pd
import pytest

from src import config
from src.drift.monitor import (
    apply_persistence,
    baseline_test,
    bh_reject,
    data_quality_checks,
    residual_checks,
    season_aware_test,
    severity,
)
from src.drift.policy import recommend

CFG = config.load_yaml("drift")
GOV = config.load_yaml("governance")


def seasonal_series(years=8, offset_from=None, offset=0.0, seed=0):
    """Stationary seasonal signal with year-to-year noise; optional step change."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=365 * years, freq="D")
    doy = idx.dayofyear.to_numpy()
    year_anom = pd.Series(rng.normal(0, 0.6, years + 1), index=range(2015, 2015 + years + 1))
    y = 10 * np.sin(2 * np.pi * (doy - 100) / 365.25) + year_anom.loc[idx.year].to_numpy() + rng.normal(0, 1, len(idx))
    s = pd.Series(y, index=idx)
    if offset_from is not None:
        s.loc[offset_from:] += offset
    return s


def test_bh_controls_rejections():
    # m=3 valid: thresholds 0.0167, 0.0333, 0.05 -> 0.001 and 0.03 rejected, 0.2 not
    assert bh_reject([0.001, 0.2, 0.03, np.nan], 0.05) == [True, False, True, False]
    assert bh_reject([0.001, 0.2, 0.04], 0.05) == [True, False, False]
    assert bh_reject([0.01, 0.02, 0.03, 0.04], 0.05) == [True, True, True, True]
    assert bh_reject([np.nan, np.nan], 0.05) == [False, False]


def test_season_aware_false_positive_rate_at_seasonal_transition():
    """At a steep seasonal rise with no drift, the season-aware test should reject at about the
    nominal rate; the season-blind baseline rejects essentially always."""
    T = pd.Timestamp("2021-06-15")
    p_season, p_base = [], []
    for seed in range(200):
        s = seasonal_series(seed=seed)
        p_season.append(season_aware_test(s, T, CFG)[1])
        p_base.append(baseline_test(s, T, CFG)[1])
    assert np.mean(np.array(p_season) < 0.05) < 0.10
    assert np.mean(np.array(p_base) < 0.05) > 0.95


def test_season_aware_detects_real_shift():
    s = seasonal_series(offset_from="2021-05-01", offset=6.0)
    _, p, _ = season_aware_test(s, pd.Timestamp("2021-06-15"), CFG)
    assert p < 0.01


def test_season_aware_requires_reference_years():
    s = seasonal_series(years=3)
    z, p, d = season_aware_test(s, pd.Timestamp("2017-06-15"), CFG)
    assert np.isnan(p) and d["status"] == "insufficient_data"


def test_window_with_many_missing_days_is_not_tested():
    s = seasonal_series()
    s.loc["2021-05-20":"2021-06-15"] = np.nan
    _, p, d = season_aware_test(s, pd.Timestamp("2021-06-15"), CFG)
    assert np.isnan(p)


def test_persistence_requires_consecutive_flags():
    f = pd.DataFrame(
        {
            "check_date": [f"2021-01-{d:02d}" for d in (1, 8, 15, 22, 29)],
            "kind": "covariate",
            "detector": "season_aware",
            "target": "t_mean7",
            "flagged": [True, False, True, True, True],
        }
    )
    out = apply_persistence(f, k_cov=2, k_res=2)
    assert out["alert"].tolist() == [False, False, False, True, True]


def _preds(n_days=900, scale_after=None, scale=1.0):
    rng = np.random.default_rng(1)
    t = pd.date_range("2021-01-01", periods=n_days)
    obs = 50 + 30 * np.sin(2 * np.pi * t.dayofyear / 365.25) + rng.normal(0, 3, n_days)
    p50 = obs + rng.normal(0, 3, n_days)
    df = pd.DataFrame({"target_date": t, "h": 1, "obs": obs, "p10": p50 - 5, "p50": p50, "p90": p50 + 5})
    if scale_after:
        df.loc[df["target_date"] >= scale_after, "obs"] *= scale
    return df


def test_residual_drift_flags_rating_shift_and_respects_observation_lag():
    cfg = {**CFG, "residual": {**CFG["residual"], "horizons": [1]}}
    clean = residual_checks(_preds(), pd.Timestamp("2023-03-01"), cfg)
    assert not any(f.flagged for f in clean if f.detector == "season_aware")
    shifted = residual_checks(_preds(scale_after="2023-01-15", scale=1.5), pd.Timestamp("2023-03-01"), cfg)
    assert any(f.flagged for f in shifted if f.detector == "season_aware")
    # An observation for the check date itself is not yet available (1-day lag).
    late = _preds(scale_after="2023-03-01", scale=3.0)
    f = residual_checks(late, pd.Timestamp("2023-03-01"), cfg)
    assert not any(x.flagged for x in f if x.detector == "season_aware")


def test_stuck_sensor_and_missing_inputs_are_data_quality_not_drift(table, daily):
    T = pd.Timestamp("2019-08-01")
    d = daily.copy()
    d.loc["2019-07-20":"2019-08-01", "temperature_2m"] = 4.2
    t = table.copy()
    t.loc["2019-07-10":"2019-08-01", "flag_q_missing"] = 1
    out = {(f.kind, f.target): f.flagged for f in data_quality_checks(t, d, T, CFG)}
    assert out[("pipeline", "temperature_2m")]
    assert out[("data_quality", "discharge")]
    assert not out[("data_quality", "era5")]


@pytest.mark.parametrize(
    "rows,tier",
    [
        ([], 0),
        ([("pipeline", "temperature_2m", 13.0)], 1),
        ([("residual", "h1", 1.2)], 2),
        ([("residual", "h7", 3.1)], 3),
        ([("covariate", "t_mean7", 4.0)], 0),
        ([("data_quality", "modis", 0.5), ("residual", "h7", 3.0)], 1),
    ],
)
def test_policy_tiers(rows, tier):
    a = pd.DataFrame(rows, columns=["kind", "target", "statistic"])
    assert recommend(a, GOV["retraining"], CFG["residual"]["qs_ratio_alert"])["tier"] == tier


def test_severity_levels():
    assert severity(pd.DataFrame(columns=["kind"])) == "none"
    assert severity(pd.DataFrame({"kind": ["covariate"]})) == "info"
    assert severity(pd.DataFrame({"kind": ["residual"]})) == "warning"
    assert severity(pd.DataFrame({"kind": ["pipeline"]})) == "critical"
