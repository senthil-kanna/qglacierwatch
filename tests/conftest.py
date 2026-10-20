import pandas as pd
import pytest

from src import config
from src.data.synthetic import generate
from src.features.build import build_features, merge_daily


@pytest.fixture(scope="session")
def cfg():
    return config.load_yaml("forecast")


@pytest.fixture(scope="session")
def frames():
    """SYNTHETIC raw tables (2015-2022 keeps tests fast)."""
    return generate("2015-01-01", "2022-12-31", seed=3)


@pytest.fixture(scope="session")
def daily(frames):
    return merge_daily(frames, "2015-01-01", "2022-12-31")


@pytest.fixture(scope="session")
def table(daily, cfg):
    return build_features(daily, cfg["availability_lag_days"], cfg["horizons"]).iloc[cfg["warmup_days"] :]


@pytest.fixture
def small_cfg(cfg):
    c = dict(cfg)
    c["splits"] = {
        "train": ["2015-01-01", "2019-12-31"],
        "calibration": ["2020-01-01", "2021-06-30"],
        "test": ["2021-07-01", "2022-12-31"],
    }
    return c


@pytest.fixture
def idx(table):
    return lambda a, b: table.index[(table.index >= pd.Timestamp(a)) & (table.index <= pd.Timestamp(b))]
