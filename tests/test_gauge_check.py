"""Gauge cleaning rules on SYNTHETIC 15-minute readings (no real gauge data in the repository)."""

import numpy as np
import pandas as pd
import pytest

from src.evaluate.gauge_check import daily_means, flag_readings, load_readings, pair_metrics

COLS = ["Station", "Latitude", "Longitude", "Data Acquisition Time", "Telemetry Hourly River Water Discharge (m3/sec)"]


def write_csv(path, rows):
    pd.DataFrame(rows, columns=COLS).to_csv(path, index=False)


def readings(start, n, value, step="15min"):
    t = pd.date_range(start, periods=n, freq=step)
    return [["Bajoura Bridge", 31.85, 77.17, x.strftime("%d-%m-%Y %H:%M"), value] for x in t]


def test_load_converts_ist_to_utc_and_drops_invalid(tmp_path):
    rows = readings("2024-01-01 05:30", 2, 100) + [["Bajoura Bridge", 31.85, 77.17, "01-01-2024 06:00", "-"],
                                                   ["Bajoura Bridge", 31.85, 77.17, "01-01-2024 06:15", -5],
                                                   ["Other", 0, 0, "01-01-2024 06:15", 1]]
    write_csv(tmp_path / "a.csv", rows)
    r = load_readings([tmp_path / "a.csv"])
    assert len(r) == 4 and r["t"].iloc[0] == pd.Timestamp("2024-01-01 00:00")
    assert r["v"].isna().sum() == 2


def test_daily_mean_needs_48_readings_and_flags_are_kept_not_removed(tmp_path):
    day1 = readings("2024-01-01 05:30", 96, 100)          # full UTC day 2024-01-01
    day2 = readings("2024-01-02 05:30", 40, 100)          # too few readings
    day3 = readings("2024-01-03 05:30", 96, 100)
    day3[50][4] = 900                                      # isolated spike
    write_csv(tmp_path / "a.csv", day1 + day2 + day3)
    d = daily_means(flag_readings(load_readings([tmp_path / "a.csv"])))
    assert list(d.index.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-01-03"]
    assert bool(d.loc["2024-01-03", "spike"]) and d.loc["2024-01-03", "obs"] > 100   # flagged, value kept
    assert bool(d.loc["2024-01-01", "flatline"])           # 96 identical readings


def test_pair_metrics_ratios():
    o = pd.Series([100.0, 200.0, 300.0])
    m = pair_metrics(o, o * 0.5)
    assert m["bias_ratio"] == pytest.approx(0.5) and m["median_ratio"] == pytest.approx(0.5) and m["r"] == pytest.approx(1.0)
    assert np.isfinite(m["nse"]) and m["nse"] < 1
