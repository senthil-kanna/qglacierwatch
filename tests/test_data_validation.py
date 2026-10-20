import json

import numpy as np
import pandas as pd

from src.data.synthetic import SOURCE, generate
from src.ingest.provenance import record_or_verify
from src.validate.checks import completeness, validate_all, validate_frame


def test_synthetic_is_deterministic_and_labelled():
    a = generate("2020-01-01", "2020-12-31", seed=1)
    b = generate("2020-01-01", "2020-12-31", seed=1)
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])
    assert (a["discharge"]["source"] == SOURCE).all()


def test_synthetic_passes_schema(frames):
    report = validate_all(frames, "2015-01-01", "2022-12-31")
    assert report["ok"], json.dumps(report)[:500]


def test_out_of_range_and_units_are_caught(frames):
    bad = frames["era5_land"].copy()
    bad.loc[5, "temperature_2m"] = 280.0  # Kelvin not converted
    _, failures = validate_frame("era5_land", bad)
    assert any(f["column"] == "temperature_2m" for f in failures)

    q = frames["discharge"].copy()
    q.loc[3, "discharge_m3s"] = -5.0
    _, failures = validate_frame("discharge", q)
    assert failures


def test_duplicate_dates_fail(frames):
    q = pd.concat([frames["discharge"], frames["discharge"].iloc[:1]], ignore_index=True)
    report = validate_all({"discharge": q}, "2015-01-01", "2022-12-31")
    assert not report["ok"]


def test_completeness_reports_gaps():
    dates = pd.date_range("2020-01-01", "2020-01-31").delete([5, 6, 7, 20])
    df = pd.DataFrame({"date": dates, "x": np.ones(len(dates))})
    c = completeness("t", df, "2020-01-01", "2020-01-31")
    assert c["missing_dates"] == 4
    assert c["longest_missing_run_days"] == 3


def test_refresh_never_overwrites_recorded_raw_files(tmp_path):
    from src.pipeline.refresh import stage_and_merge

    raw, staging = tmp_path / "raw", tmp_path / "staging"
    raw.mkdir()
    staging.mkdir()
    (raw / "era5_land.parquet").write_bytes(b"trained-on")
    record_or_verify(raw)
    (staging / "era5_land.parquet").write_bytes(b"re-downloaded, different")
    (staging / "new_source.parquet").write_bytes(b"new")
    merge = stage_and_merge(raw, staging)
    assert merge["changed"] == ["era5_land.parquet"]
    assert merge["added"] == ["new_source.parquet"]
    assert (raw / "era5_land.parquet").read_bytes() == b"trained-on"


def test_provenance_detects_changed_raw_file(tmp_path):
    p = tmp_path / "discharge.parquet"
    p.write_bytes(b"version-1")
    assert record_or_verify(tmp_path)["status"] == "recorded"
    assert record_or_verify(tmp_path)["status"] == "verified"
    p.write_bytes(b"version-2")
    r = record_or_verify(tmp_path)
    assert r["status"] == "conflict" and r["conflicts"] == ["discharge.parquet"]
