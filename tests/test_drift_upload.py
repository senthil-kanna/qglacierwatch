import io

import numpy as np
import pandas as pd
import pytest

from src import config
from src.drift.upload import scenario_daily, validate

ARCHIVE = (pd.Timestamp("2015-01-01"), pd.Timestamp("2022-12-31"))
SAMPLES = config.ROOT / "dashboard" / "samples"


def upload(start="2022-06-01", days=40, **cols) -> pd.DataFrame:
    dates = pd.date_range(start, periods=days, freq="D")
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "temperature_2m": 10.0, "precipitation": 2.0, "snow_frac": 0.3,
                       "discharge": 150.0 + np.arange(days)})
    return df.assign(**cols)


def errors(df) -> list[str]:
    return validate(df, 30, ARCHIVE)[1]


def test_valid_upload_passes_and_is_indexed_by_date():
    df, errs, warns = validate(upload(), 30, ARCHIVE)
    assert errs == [] and warns == []
    assert df.index.name == "date" and len(df) == 40


def test_column_names_are_case_and_space_insensitive_and_extras_are_reported():
    raw = upload().rename(columns={"discharge": " Discharge "}).assign(station="x")
    df, errs, warns = validate(raw, 30, ARCHIVE)
    assert errs == [] and any("station" in w for w in warns)


@pytest.mark.parametrize(
    ("df", "needle"),
    [
        (upload().drop(columns="discharge"), "missing column(s): discharge"),
        (upload(days=20), "at least 30"),
        (upload(snow_frac=1.5), "snow_frac"),
        (upload(discharge=-1.0), "discharge"),
        (upload(start="2016-06-01"), "must lie between"),  # fewer than 4 past seasons
        (upload(start="2023-03-01"), "must lie between"),  # gap after the archive end
        (upload().drop(index=[5, 6]), "consecutive"),
        (upload().assign(date="not a date"), "unreadable date"),
    ],
)
def test_invalid_uploads_are_rejected_with_a_reason(df, needle):
    assert any(needle in e for e in errors(df))


def test_missing_values_are_warnings_not_errors():
    df = upload()
    df.loc[3:5, "temperature_2m"] = np.nan
    clean, errs, warns = validate(df, 30, ARCHIVE)
    assert errs == [] and any("temperature_2m" in w for w in warns)


def test_scenario_overwrites_uploaded_days_and_keeps_the_rest(daily):
    up = validate(upload(temperature_2m=25.0), 30, ARCHIVE)[0]
    s = scenario_daily(up, daily)
    days = up.index
    assert (s.loc[days, "temperature_2m"] == 25.0).all()
    assert (s.loc[days, "discharge_m3s"] == up["discharge"]).all()
    shift = 25.0 - daily.loc[days, "temperature_2m"]
    assert np.allclose(s.loc[days, "temperature_2m_max"], daily.loc[days, "temperature_2m_max"] + shift)
    outside = s.index.difference(days)
    pd.testing.assert_frame_equal(s.loc[outside], daily.loc[outside], check_freq=False)
    assert (daily.loc[days, "temperature_2m"] != 25.0).any(), "archive copy must not be modified"


def test_scenario_extends_past_archive_with_climatology(daily):
    up = validate(upload(start="2022-12-20", days=40), 30, ARCHIVE)[0]
    s = scenario_daily(up, daily)
    assert s.index.max() == up.index.max()
    new = s.loc["2023-01-01":]
    assert new[["snowmelt_sum", "snow_depth_water_equivalent"]].notna().all().all()
    assert (new["discharge_m3s"] == up.loc["2023-01-01":, "discharge"]).all()


def _real_ready() -> bool:
    try:
        from src.serving.store import Store

        return (config.raw_dir("real") / "discharge.parquet").exists() and Store("real").serving_model()[0] is not None
    except Exception:
        return False


@pytest.mark.skipif(not _real_ready(), reason="needs the real archive and a registered model")
def test_samples_give_the_documented_verdicts_every_time():
    from src.drift.upload import check
    from src.serving.store import Store

    model_id, _, bundle = Store("real").serving_bundle()
    verdicts = {}
    for name in ("normal_data", "changed_data"):
        raw = (SAMPLES / f"{name}.csv").read_bytes()
        runs = [check(pd.read_csv(io.BytesIO(raw), comment="#"), "real", bundle, model_id) for _ in range(2)]
        assert runs[0]["light"] == runs[1]["light"] and runs[0]["recommendation"] == runs[1]["recommendation"]
        verdicts[name] = runs[0]
    assert verdicts["normal_data"]["light"] == "green" and verdicts["normal_data"]["recommendation"]["tier"] == 0
    changed = verdicts["changed_data"]
    assert changed["light"] == "red" and changed["recommendation"]["tier"] == 3
    # Margin, so a refreshed reference period does not flip the demo verdicts.
    assert (verdicts["normal_data"]["residual"]["statistic"] < 1.5).all()
    assert (changed["residual"]["statistic"] > 3.0).all()


def test_sample_files_are_labelled_synthetic():
    for name in ("normal_data.csv", "changed_data.csv"):
        assert (SAMPLES / name).read_text().startswith("# SYNTHETIC")
