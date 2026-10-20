"""Data-version extension (append-only) and config overlays."""

import pandas as pd
import pytest

from src import config
from src.ingest.extend import append_rows


def frame(start, end, value=1.0):
    d = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"date": d, "x": value, "source": "s"})


def test_append_rows_keeps_old_values_and_stops_at_until():
    old = frame("2025-12-01", "2025-12-31", 1.0)
    new = frame("2025-12-20", "2026-01-10", 2.0)   # overlaps the old range and runs past `until`
    out, info = append_rows(old, new, pd.Timestamp("2026-01-05"))
    assert (out.set_index("date").loc[:"2025-12-31", "x"] == 1.0).all()   # nothing overwritten
    assert out["date"].max() == pd.Timestamp("2026-01-05")
    assert info["rows_added"] == 5 and info["missing_dates"] == []


def test_append_rows_reports_gaps_and_rejects_missing_columns():
    old = frame("2025-12-01", "2025-12-31")
    new = frame("2026-01-01", "2026-01-05").drop(index=2)
    _, info = append_rows(old, new, pd.Timestamp("2026-01-05"))
    assert info["missing_dates"] == ["2026-01-03"]
    with pytest.raises(ValueError, match="lack columns"):
        append_rows(old, new.drop(columns="x"), pd.Timestamp("2026-01-05"))


def test_overlay_changes_only_listed_keys(monkeypatch):
    base = config.load_yaml("forecast")
    monkeypatch.setenv("QGW_CONFIG_OVERLAY", "configs/fresh2026")
    over = config.load_yaml("forecast")
    assert over["splits"]["test"] == ["2026-01-01", "2026-09-30"]
    assert over["cv_validation_years"] == [2020, 2021, 2022, 2023]
    for k in base:
        if k not in ("splits", "cv_validation_years"):
            assert over[k] == base[k], k
    assert config.overlay_file("governance") is None   # no overlay file -> base config unchanged
