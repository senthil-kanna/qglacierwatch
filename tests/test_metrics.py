import numpy as np
import pytest

from src.evaluate.bootstrap import block_bootstrap_diff
from src.evaluate.metrics import (
    coverage,
    kge,
    mae,
    nse,
    pinball,
    quantile_score,
    rmse,
    score_all,
    score_by_season,
)
from src.models.calibration import CQR


def test_perfect_forecast_scores():
    o = np.array([1.0, 2.0, 3.0, 4.0])
    assert nse(o, o) == pytest.approx(1.0)
    assert kge(o, o) == pytest.approx(1.0)
    assert mae(o, o) == 0 and rmse(o, o) == 0


def test_mean_forecast_has_zero_nse():
    o = np.array([1.0, 2.0, 3.0, 4.0])
    assert nse(o, np.full(4, o.mean())) == pytest.approx(0.0)


@pytest.mark.parametrize("obs", [np.full(5, 3.0), np.array([2.0]), np.array([])])
def test_undefined_scores_are_nan(obs):
    sim = np.ones(len(obs))
    assert np.isnan(nse(obs, sim))
    assert np.isnan(kge(obs, sim))


def test_kge_nan_when_simulation_constant():
    assert np.isnan(kge(np.array([1.0, 2.0, 3.0]), np.array([2.0, 2.0, 2.0])))


def test_nan_pairs_are_dropped():
    o = np.array([1.0, np.nan, 3.0, 4.0])
    s = np.array([1.0, 2.0, np.nan, 4.0])
    assert mae(o, s) == 0


def test_pinball_and_quantile_score():
    assert pinball(10.0, 8.0, 0.9) == pytest.approx(1.8)
    assert pinball(10.0, 12.0, 0.9) == pytest.approx(0.2)
    q = np.array([[5.0, 5.0, 5.0]])
    # point forecast: QS reduces to mean of 2*pinball = absolute error averaged over taus
    assert quantile_score(np.array([5.0]), q)[0] == 0
    assert quantile_score(np.array([7.0]), q)[0] == pytest.approx(np.mean([2 * 0.1 * 2, 2 * 0.5 * 2, 2 * 0.9 * 2]))


def test_coverage_and_score_all():
    o = np.array([1.0, 2.0, 3.0, 4.0])
    assert coverage(o, o - 1, o + 1) == 1.0
    q = np.column_stack([o + 0.5, o + 1, o + 2])
    s = score_all(o, q)
    assert s["coverage_80"] == 0 and s["n"] == 4 and s["crossing_rate"] == 0
    assert score_all(np.array([np.nan]), np.array([[1.0, 2.0, 3.0]]))["n"] == 0


def test_seasonal_breakdown_uses_target_dates():
    import pandas as pd

    dates = pd.date_range("2020-01-01", periods=366)
    o = np.arange(366, dtype=float) + 1
    q = np.column_stack([o, o, o])
    seasons = {"winter": [12, 1, 2], "pre_monsoon": [3, 4, 5], "monsoon": [6, 7, 8, 9], "post_monsoon": [10, 11]}
    s = score_by_season(dates, o, q, seasons)
    assert sum(v["n"] for v in s.values()) == 366
    assert s["monsoon"]["n"] == 122


def test_block_bootstrap_detects_clear_difference():
    rng = np.random.default_rng(0)
    a = rng.normal(1.0, 0.2, 500)
    b = a + 0.5
    r = block_bootstrap_diff(a, b, block=20, n=300)
    assert r["hi"] < 0 and r["p_a_better"] == 1.0
    r2 = block_bootstrap_diff(a, a + rng.normal(0, 0.2, 500), block=20, n=300)
    assert r2["lo"] < 0 < r2["hi"]


def test_cqr_reaches_target_coverage_on_exchangeable_data():
    rng = np.random.default_rng(1)
    y = np.exp(rng.normal(3, 0.5, 4000))
    narrow = np.column_stack([np.full(4000, np.exp(2.9)), np.full(4000, np.exp(3)), np.full(4000, np.exp(3.1))])
    cqr = CQR(0.8).fit(y[:2000], narrow[:2000])
    adj = cqr.apply(narrow[2000:])
    assert cqr.q_hat > 0
    assert coverage(y[2000:], adj[:, 0], adj[:, 2]) == pytest.approx(0.8, abs=0.03)
    assert np.all(adj[:, 0] <= adj[:, 1]) and np.all(adj[:, 1] <= adj[:, 2])


def test_cqr_can_narrow_overwide_intervals_without_crossing():
    y = np.full(100, 10.0)
    wide = np.column_stack([np.full(100, 1.0), np.full(100, 10.0), np.full(100, 100.0)])
    adj = CQR(0.8).fit(y, wide).apply(wide)
    assert np.all(adj[:, 0] <= adj[:, 1]) and np.all(adj[:, 2] >= adj[:, 1])
    assert np.all(adj[:, 2] - adj[:, 0] < 99)
