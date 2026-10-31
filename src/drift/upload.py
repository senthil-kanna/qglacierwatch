"""What-if drift check on a user-supplied CSV (dashboard "Upload and check").

The uploaded days are overlaid on a copy of the raw archive, features are rebuilt, the serving
model forecasts the uploaded days, and the unchanged weekly monitors (src.drift.replay.run_checks)
and retraining policy (src.drift.policy.recommend) decide the tier. Nothing is written: the archive,
feature store, registry and S3 are never modified, and no model is retrained or promoted.

CSV columns: date, temperature_2m (deg C), precipitation (mm/day), snow_frac (0-1), discharge (m3/s).
Inputs the CSV does not carry (Tmin/Tmax, snowfall, snowmelt, SWE, MODIS valid fraction) keep their
archive values on overlapping days and take the day-of-year climatology on days after the archive;
Tmin/Tmax move with the uploaded mean temperature.
"""

import numpy as np
import pandas as pd

from src import config
from src.drift.monitor import severity
from src.drift.policy import recommend
from src.drift.replay import out_of_sample, run_checks
from src.features.build import build_features, load_raw, merge_daily

COLUMNS = {
    "temperature_2m": ("temperature_2m", -60.0, 50.0),
    "precipitation": ("total_precipitation_sum", 0.0, 500.0),
    "snow_frac": ("snow_frac_valid", 0.0, 1.0),
    "discharge": ("discharge_m3s", 0.0, 50000.0),
}
MAX_DAYS = 366
MIN_REFERENCE_YEARS_BEFORE = 4  # season-aware covariate test needs this many past years


def validate(raw: pd.DataFrame, window_days: int, archive: tuple[pd.Timestamp, pd.Timestamp]) -> tuple[pd.DataFrame | None, list[str], list[str]]:
    """Returns (clean frame indexed by date, errors, warnings). Any error means no check is run."""
    errors: list[str] = []
    warnings: list[str] = []
    raw = raw.rename(columns=lambda c: str(c).strip().lower())
    missing = [c for c in ("date", *COLUMNS) if c not in raw.columns]
    if missing:
        return None, [f"missing column(s): {', '.join(missing)}"], warnings
    extra = [c for c in raw.columns if c not in ("date", *COLUMNS)]
    if extra:
        warnings.append(f"ignored column(s): {', '.join(extra)}")
    df = raw[["date", *COLUMNS]].reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="ISO8601")
    if df["date"].isna().any():
        errors.append(f"{int(df['date'].isna().sum())} row(s) with an unreadable date (use YYYY-MM-DD)")
        return None, errors, warnings
    if df["date"].duplicated().any():
        errors.append(f"duplicate date(s): {', '.join(str(d.date()) for d in df.loc[df['date'].duplicated(), 'date'][:5])}")
    df = df.sort_values("date").set_index("date")
    for c, (_, lo, hi) in COLUMNS.items():
        df[c] = pd.to_numeric(df[c], errors="coerce")
        bad = df[c].notna() & ((df[c] < lo) | (df[c] > hi) | ((c == "discharge") & (df[c] <= 0)))
        if bad.any():
            errors.append(f"{c}: {int(bad.sum())} value(s) outside the physical range [{lo:g}, {hi:g}]")
        frac = float(df[c].isna().mean())
        if frac > 0:
            warnings.append(f"{c}: {frac:.0%} missing")
    if errors:
        return None, errors, warnings
    span = (df.index.max() - df.index.min()).days + 1
    if span != len(df):
        errors.append(f"dates must be consecutive days: {span - len(df)} day(s) missing between {df.index.min().date()} and {df.index.max().date()}")
    if len(df) < window_days:
        errors.append(f"{len(df)} days uploaded; at least {window_days} are needed (one monitoring window)")
    if len(df) > MAX_DAYS:
        errors.append(f"{len(df)} days uploaded; at most {MAX_DAYS}")
    first_ok = archive[0] + pd.DateOffset(years=MIN_REFERENCE_YEARS_BEFORE)
    last_ok = archive[1] + pd.Timedelta(days=1)
    if df.index.min() < first_ok or df.index.min() > last_ok:
        errors.append(
            f"first date {df.index.min().date()} must lie between {first_ok.date()} and {last_ok.date()}: "
            "the upload has to continue (or replace part of) the archive so the monitors have past seasons to compare with"
        )
    return (None if errors else df), errors, warnings


def _climatology(daily: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    doy = daily.groupby(daily.index.dayofyear).mean()
    return doy.reindex(np.minimum(dates.dayofyear, 365)).set_axis(dates)


def scenario_daily(upload: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Archive daily table with the uploaded days written over it (extended past its end if needed)."""
    idx = pd.date_range(daily.index.min(), max(daily.index.max(), upload.index.max()), freq="D", name="date")
    out = daily.reindex(idx)
    new = idx[idx > daily.index.max()]
    if len(new):
        out.loc[new] = _climatology(daily, new).to_numpy()
    days = upload.index
    t_old = out.loc[days, "temperature_2m"]
    for c, (target, _, _) in COLUMNS.items():
        out.loc[days, target] = upload[c].to_numpy()
    shift = (out.loc[days, "temperature_2m"] - t_old).fillna(0.0)
    out.loc[days, ["temperature_2m_min", "temperature_2m_max"]] = out.loc[days, ["temperature_2m_min", "temperature_2m_max"]].add(shift, axis=0)
    # Snowfall cannot exceed total precipitation; a missing snow observation is a missing MODIS day.
    out.loc[days, "snowfall_sum"] = np.minimum(out.loc[days, "snowfall_sum"], out.loc[days, "total_precipitation_sum"].fillna(np.inf))
    # An uploaded snow fraction counts as a valid observation even where MODIS was cloud-covered.
    seen = upload["snow_frac"].notna().to_numpy()
    out.loc[days[seen], "valid_frac"] = out.loc[days[seen], "valid_frac"].fillna(1.0)
    out.loc[days[~seen], "valid_frac"] = np.nan
    return out


def forecast_upload(bundle: dict, table: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, horizons: list[int]) -> pd.DataFrame:
    """Serving-model forecasts whose target day falls inside the uploaded window."""
    rows = []
    for h in horizons:
        issues = pd.date_range(start - pd.Timedelta(days=h), end - pd.Timedelta(days=h), freq="D")
        issues = issues[issues.isin(table.index)]
        q = np.mean([m.predict(table, issues) for m in bundle["models"][h]], axis=0)
        q = bundle["cqr"][h].apply(np.sort(q, axis=1), issues + pd.Timedelta(days=h))
        rows.append(pd.DataFrame({"issue_date": issues, "target_date": issues + pd.Timedelta(days=h), "h": h,
                                  "obs": table.loc[issues, f"y_h{h}"].to_numpy(), "p10": q[:, 0], "p50": q[:, 1], "p90": q[:, 2]}))
    return pd.concat(rows, ignore_index=True)


def light(rec: dict, alerts: pd.DataFrame) -> str:
    """green: no alert; amber: alerts that do not justify retraining (Tier 0 covariate, 1, 2); red: Tier 3."""
    if rec["tier"] == 3:
        return "red"
    return "amber" if not alerts.empty else "green"


def check(raw: pd.DataFrame, mode: str, bundle: dict, model_id: str) -> dict:
    cfg = config.load_yaml("drift")
    fcfg = config.load_yaml("forecast")
    gov = config.load_yaml("governance")
    frames = load_raw(mode)
    start = min(f["date"].min() for f in frames.values())
    end = max(f["date"].max() for f in frames.values())
    daily = merge_daily(frames, str(start.date()), str(end.date()))
    upload, errors, warnings = validate(raw, cfg["window_days"], (start, end))
    result = {"ok": upload is not None, "errors": errors, "warnings": warnings, "archive": [str(start.date()), str(end.date())]}
    if upload is None:
        return result

    lags = fcfg["availability_lag_days"]
    scen = scenario_daily(upload, daily)
    table = build_features(scen, lags, fcfg["horizons"]).iloc[fcfg["warmup_days"]:]
    u0, T = upload.index.min(), upload.index.max()
    horizons = cfg["residual"]["horizons"]
    new = forecast_upload(bundle, table, u0, T, horizons)
    ref, _ = out_of_sample(mode)
    preds = new if ref is None else pd.concat([ref[(ref["target_date"] < u0) & ref["h"].isin(horizons)], new], ignore_index=True)

    dates = [T - pd.Timedelta(days=cfg["check_every_days"]), T]
    f = run_checks(table, scen, preds, dates, cfg, lags)
    now = f[(f["check_date"] == str(T.date())) & f["alert"] & (f["detector"] != "baseline")]
    rec = recommend(now, gov["retraining"], cfg["residual"]["qs_ratio_alert"])
    res = f[(f["check_date"] == str(T.date())) & (f["kind"] == "residual") & (f["detector"] == "season_aware")]
    archive_new = (upload.index > end).sum()
    if archive_new:
        warnings.append(f"{archive_new} uploaded day(s) are after the archive end ({end.date()}); "
                        "Tmin/Tmax, snowfall, snowmelt and SWE on those days come from the seasonal climatology")
    return {
        **result,
        "warnings": warnings,
        "model_id": model_id,
        "window": [str(u0.date()), str(T.date())],
        "n_days": len(upload),
        "check_date": str(T.date()),
        "light": light(rec, now),
        "severity": severity(now),
        "recommendation": rec,
        "alerts": now,
        "findings": f[f["check_date"] == str(T.date())],
        "residual": res,
        "forecasts": new,
        "upload": upload,
    }
