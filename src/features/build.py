"""Build the versioned, leakage-safe feature table from raw daily inputs.

Every row is an issue date t. Each source is first shifted by its availability lag, so a feature
at row t only uses values that would have been published by day t. Rolling windows and gap
filling run on the shifted series and look backwards only. Targets y_h{h} are the discharge on
t+h and are never used to build features.

Usage:
    python -m src.features.build                # mode from QGW_MODE (default real)
    python -m src.features.build --mode demo
"""

import argparse
import hashlib
import json

import numpy as np
import pandas as pd

from src import config
from src.validate.checks import validate_all

ERA5_COLS = [
    "temperature_2m",
    "temperature_2m_min",
    "temperature_2m_max",
    "total_precipitation_sum",
    "snowfall_sum",
    "snowmelt_sum",
    "snow_depth_water_equivalent",
]
MODIS_COLS = ["snow_frac_valid", "valid_frac", "snow_frac_basin", "ndsi_mean"]

# Daily variables fed to the LSTM as a sequence (all already availability-shifted).
SEQ_COLS = [
    "seq_logq",
    "seq_t",
    "seq_precip",
    "seq_snowfall",
    "seq_melt",
    "seq_snow_frac",
    "seq_snow_age",
    "seq_valid_frac",
    "doy_sin",
    "doy_cos",
]


def load_raw(m: str) -> dict[str, pd.DataFrame]:
    raw = config.raw_dir(m)
    frames = {name: pd.read_parquet(raw / f"{name}.parquet") for name in ("modis_snow", "era5_land", "discharge")}
    for df in frames.values():
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).astype("datetime64[ns]")
    return frames


def merge_daily(frames: dict[str, pd.DataFrame], start: str, end: str) -> pd.DataFrame:
    idx = pd.date_range(start, end, freq="D", name="date")
    q = frames["discharge"].set_index("date")["discharge_m3s"].reindex(idx)
    era5 = frames["era5_land"].set_index("date")[ERA5_COLS].reindex(idx)
    modis = frames["modis_snow"].set_index("date")[MODIS_COLS].reindex(idx)
    for col in ["total_precipitation_sum", "snowfall_sum", "snowmelt_sum"]:
        era5[col] = era5[col].clip(lower=0.0)  # ERA5 accumulations have ~1e-5 mm negative noise
    daily = pd.concat([q.rename("discharge_m3s"), era5, modis], axis=1)
    return daily


def _days_since_valid(valid: pd.Series) -> pd.Series:
    """Days since the last non-NaN value, counted causally (NaN before the first observation)."""
    pos = pd.Series(np.where(valid.notna(), np.arange(len(valid)), np.nan), index=valid.index).ffill()
    return pd.Series(np.arange(len(valid)), index=valid.index) - pos


def build_features(daily: pd.DataFrame, lags: dict, horizons: list[int]) -> pd.DataFrame:
    q = daily["discharge_m3s"].shift(lags["discharge"])
    era = daily[ERA5_COLS].shift(lags["era5"])
    mod = daily[MODIS_COLS].shift(lags["modis"])

    f = pd.DataFrame(index=daily.index)
    logq = np.log(q)
    f["q0"] = q
    f["logq0"] = logq
    for k in (1, 2, 6, 13, 29):
        f[f"logq_lag{k}"] = logq.shift(k)
    f["logq_mean7"] = logq.rolling(7, min_periods=5).mean()
    f["logq_mean30"] = logq.rolling(30, min_periods=20).mean()
    f["logq_trend7"] = logq - logq.shift(7)

    t = era["temperature_2m"]
    pdd = t.clip(lower=0.0)
    rain = (era["total_precipitation_sum"] - era["snowfall_sum"]).clip(lower=0.0)
    for w in (3, 7, 30):
        f[f"t_mean{w}"] = t.rolling(w, min_periods=w).mean()
        f[f"p_sum{w}"] = era["total_precipitation_sum"].rolling(w, min_periods=w).sum()
    f["t_max7"] = era["temperature_2m_max"].rolling(7, min_periods=7).max()
    f["pdd7"] = pdd.rolling(7, min_periods=7).sum()
    f["pdd30"] = pdd.rolling(30, min_periods=30).sum()
    f["rain7"] = rain.rolling(7, min_periods=7).sum()
    f["snowfall30"] = era["snowfall_sum"].rolling(30, min_periods=30).sum()
    f["melt7"] = era["snowmelt_sum"].rolling(7, min_periods=7).sum()
    f["melt30"] = era["snowmelt_sum"].rolling(30, min_periods=30).sum()
    # Absolute basin-mean SWE is dominated by ERA5-Land glacier cells (fixed deep SWE), so only
    # its change is informative.
    f["swe_change30"] = era["snow_depth_water_equivalent"] - era["snow_depth_water_equivalent"].shift(30)

    snow = mod["snow_frac_valid"]
    snow_filled = snow.ffill()
    f["snow_frac"] = snow_filled
    f["snow_age"] = _days_since_valid(snow)
    f["snow_frac_8d"] = snow.rolling(8, min_periods=1).max()
    f["snow_change30"] = snow_filled - snow_filled.shift(30)
    f["valid_frac7"] = mod["valid_frac"].rolling(7, min_periods=1).mean()

    doy = daily.index.dayofyear.to_numpy()
    f["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    f["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    # Degree-day melt scales with energy (PDD) times snow-covered area; rain on snow adds runoff.
    f["pdd7_x_snow"] = f["pdd7"] * f["snow_frac"]
    f["rain7_x_snow"] = f["rain7"] * f["snow_frac"]

    f["seq_logq"] = logq
    f["seq_t"] = t
    f["seq_precip"] = era["total_precipitation_sum"]
    f["seq_snowfall"] = era["snowfall_sum"]
    f["seq_melt"] = era["snowmelt_sum"]
    f["seq_snow_frac"] = snow_filled
    f["seq_snow_age"] = f["snow_age"].clip(upper=60)
    f["seq_valid_frac"] = mod["valid_frac"]

    # Data-availability flags exposed to monitoring (not model inputs).
    f["flag_q_missing"] = q.isna().astype(int)
    f["flag_modis_missing"] = mod["valid_frac"].isna().astype(int)
    f["flag_era5_missing"] = era["temperature_2m"].isna().astype(int)

    observed = daily["discharge_m3s"]
    for h in horizons:
        f[f"y_h{h}"] = observed.shift(-h)
    return f


FEATURE_COLS = [
    "logq0",
    "logq_lag1",
    "logq_lag2",
    "logq_lag6",
    "logq_lag13",
    "logq_lag29",
    "logq_mean7",
    "logq_mean30",
    "logq_trend7",
    "t_mean3",
    "t_mean7",
    "t_mean30",
    "p_sum3",
    "p_sum7",
    "p_sum30",
    "t_max7",
    "pdd7",
    "pdd30",
    "rain7",
    "snowfall30",
    "melt7",
    "melt30",
    "swe_change30",
    "snow_frac",
    "snow_age",
    "snow_frac_8d",
    "snow_change30",
    "valid_frac7",
    "doy_sin",
    "doy_cos",
    "pdd7_x_snow",
    "rain7_x_snow",
]


def horizon_matrix(table: pd.DataFrame, h: int) -> tuple[pd.DataFrame, pd.Series]:
    """Features for horizon h (adds the target date's season, known in advance) and its target."""
    X = table[FEATURE_COLS].copy()
    target_doy = (table.index + pd.Timedelta(days=h)).dayofyear.to_numpy()
    X["target_doy_sin"] = np.sin(2 * np.pi * target_doy / 365.25)
    X["target_doy_cos"] = np.cos(2 * np.pi * target_doy / 365.25)
    return X, table[f"y_h{h}"]


def dataset_id(table: pd.DataFrame, cfg: dict) -> str:
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(table, index=True).to_numpy().tobytes())
    h.update(json.dumps(cfg, sort_keys=True, default=str).encode())
    return h.hexdigest()[:12]


def build(m: str) -> tuple[pd.DataFrame, dict]:
    cfg = config.load_yaml("forecast")
    start, end = cfg["splits"]["train"][0], cfg["splits"]["test"][1]
    frames = load_raw(m)
    report = validate_all(frames, start, end)
    if not report["ok"]:
        raise ValueError(f"Raw data failed validation: {json.dumps(report, indent=2)[:2000]}")
    daily = merge_daily(frames, start, end)
    table = build_features(daily, cfg["availability_lag_days"], cfg["horizons"])
    table = table.iloc[cfg["warmup_days"] :]
    source = frames["discharge"]["source"].iloc[0]
    meta = {
        "mode": m,
        "dataset_id": dataset_id(table, {k: cfg[k] for k in ("availability_lag_days", "horizons", "warmup_days")}),
        "rows": len(table),
        "first_issue_date": str(table.index.min().date()),
        "last_issue_date": str(table.index.max().date()),
        "target_source": source,
        "target_is_observed": source == "gauge",
        "feature_cols": FEATURE_COLS,
        "availability_lag_days": cfg["availability_lag_days"],
        "validation": report,
    }
    return table, meta


def save(table: pd.DataFrame, meta: dict) -> str:
    out = config.processed_dir(meta["mode"])
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"features_{meta['dataset_id']}.parquet"
    if not path.exists():  # versioned by content hash: identical inputs map to the same file
        table.to_parquet(path)
    (out / f"features_{meta['dataset_id']}.json").write_text(json.dumps(meta, indent=2))
    (out / "latest.json").write_text(json.dumps({"dataset_id": meta["dataset_id"], "path": path.name}, indent=2))
    return str(path)


def load_latest(m: str) -> tuple[pd.DataFrame, dict]:
    out = config.processed_dir(m)
    latest = json.loads((out / "latest.json").read_text())
    meta = json.loads((out / f"features_{latest['dataset_id']}.json").read_text())
    return pd.read_parquet(out / latest["path"]), meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=config.mode(), choices=config.MODES)
    args = parser.parse_args()
    table, meta = build(args.mode)
    path = save(table, meta)
    v = meta["validation"]["tables"]
    print(f"[{args.mode}] dataset {meta['dataset_id']}: {meta['rows']} issue dates "
          f"{meta['first_issue_date']}..{meta['last_issue_date']}, target={meta['target_source']}")
    for name, t in v.items():
        print(f"  {name}: {t['present_days']}/{t['expected_days']} days, longest gap {t['longest_missing_run_days']} d, "
              f"NaNs {t['nan_counts']}")
    print(f"  -> {path}")


if __name__ == "__main__":
    main()
