import numpy as np
import pytest

from src.models.baselines import Climatology, Persistence
from src.models.gbm import GBMQuantile
from src.models.lstm import QuantileLSTM

GBM_SMALL = {"num_leaves": 7, "learning_rate": 0.1, "n_estimators": 60, "min_child_samples": 20}


def _check(q):
    assert q.ndim == 2 and q.shape[1] == 3
    assert np.all(np.isfinite(q)) and np.all(q > 0)
    assert np.all(q[:, 0] <= q[:, 1]) and np.all(q[:, 1] <= q[:, 2])


@pytest.mark.parametrize("h", [1, 7, 30])
def test_baselines_quantiles_ordered(table, idx, h):
    tr, te = idx("2015-01-01", "2019-11-30"), idx("2020-01-01", "2020-12-31")
    for model in (Persistence(), Climatology(15)):
        _check(model.fit(table, h, tr).predict(table, te))


def test_persistence_median_is_last_observation(table, idx):
    tr, te = idx("2015-01-01", "2019-11-30"), idx("2020-01-01", "2020-03-01")
    q = Persistence().fit(table, 7, tr).predict(table, te)
    np.testing.assert_allclose(q[:, 1], table.loc[te, "q0"])


def test_climatology_uses_only_training_period(table, idx):
    tr = idx("2015-01-01", "2017-12-31")
    a = Climatology(15).fit(table, 1, tr)
    t2 = table.copy()
    t2.loc["2018-06-01":, "y_h1"] *= 100  # future discharge changes must not affect the fit
    b = Climatology(15).fit(t2, 1, tr)
    np.testing.assert_allclose(a.table, b.table)


def test_gbm_quantiles_ordered_and_deterministic(table, idx):
    tr, te = idx("2015-01-01", "2019-11-30"), idx("2020-01-01", "2020-12-31")
    q1 = GBMQuantile(GBM_SMALL, seed=5).fit(table, 7, tr).predict(table, te)
    q2 = GBMQuantile(GBM_SMALL, seed=5).fit(table, 7, tr).predict(table, te)
    _check(q1)
    np.testing.assert_allclose(q1, q2)


@pytest.mark.slow
def test_lstm_quantiles_ordered_and_reproducible(table, idx):
    tr, te = idx("2015-01-01", "2019-11-30"), idx("2020-01-01", "2020-03-31")
    params = {"hidden": 8, "layers": 1, "dropout": 0.0, "lr": 0.01, "epochs": 3}
    m1 = QuantileLSTM(params, seq_len=20, seed=3).fit(table, 7, tr)
    m2 = QuantileLSTM(params, seq_len=20, seed=3).fit(table, 7, tr)
    q1, q2 = m1.predict(table, te), m2.predict(table, te)
    _check(q1)
    np.testing.assert_allclose(q1, q2, rtol=1e-5)
    assert m1.n_params() > 0
