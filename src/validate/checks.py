"""Schema, range and completeness checks for the raw daily inputs.

Ranges are physical plausibility limits for basin averages, not climatological bounds, so a
failure means a unit or pipeline error rather than an unusual day.
"""

import pandas as pd
import pandera.pandas as pa

# ERA5 accumulations can be marginally negative from numerical noise; tolerate down to this.
NEG_TOL = -1e-3


def _frac(nullable: bool = False) -> pa.Column:
    return pa.Column(float, pa.Check.in_range(0.0, 1.0), nullable=nullable, coerce=True)


SCHEMAS = {
    "modis_snow": pa.DataFrameSchema(
        {
            "date": pa.Column(pa.DateTime, unique=True),
            "ndsi_mean": pa.Column(float, pa.Check.in_range(0.0, 100.0), nullable=True, coerce=True),
            "snow_frac_basin": _frac(),
            "valid_frac": _frac(),
            "snow_frac_valid": _frac(nullable=True),
        }
    ),
    "era5_land": pa.DataFrameSchema(
        {
            "date": pa.Column(pa.DateTime, unique=True),
            "temperature_2m": pa.Column(float, pa.Check.in_range(-45.0, 35.0), coerce=True),
            "temperature_2m_min": pa.Column(float, pa.Check.in_range(-55.0, 35.0), coerce=True),
            "temperature_2m_max": pa.Column(float, pa.Check.in_range(-40.0, 45.0), coerce=True),
            "total_precipitation_sum": pa.Column(float, pa.Check.in_range(NEG_TOL, 400.0), coerce=True),
            "snowfall_sum": pa.Column(float, pa.Check.in_range(NEG_TOL, 400.0), coerce=True),
            "snowmelt_sum": pa.Column(float, pa.Check.in_range(NEG_TOL, 200.0), coerce=True),
            "snow_depth_water_equivalent": pa.Column(float, pa.Check.ge(0.0), coerce=True),
        },
        checks=[pa.Check(lambda d: d["temperature_2m_min"] <= d["temperature_2m_max"] + 1e-6, element_wise=False)],
    ),
    "discharge": pa.DataFrameSchema(
        {
            "date": pa.Column(pa.DateTime, unique=True),
            # Upper bound well above any recorded Beas flood at Bhuntar; catches unit mix-ups (l/s, cumecs*1000).
            "discharge_m3s": pa.Column(float, pa.Check.in_range(0.0, 10000.0), nullable=True, coerce=True),
            "source": pa.Column(str),
        }
    ),
}


def validate_frame(name: str, df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Validate one raw table. Returns the coerced frame and a list of failures (empty if clean)."""
    try:
        return SCHEMAS[name].validate(df, lazy=True), []
    except pa.errors.SchemaErrors as exc:
        cases = exc.failure_cases.head(50)
        failures = [
            {"column": str(r["column"]), "check": str(r["check"]), "failure_case": str(r["failure_case"])}
            for _, r in cases.iterrows()
        ]
        return df, failures


def completeness(name: str, df: pd.DataFrame, start: str, end: str) -> dict:
    """Missing dates, per-column NaN counts and longest gap within [start, end]."""
    expected = pd.date_range(start, end, freq="D")
    present = pd.DatetimeIndex(df["date"])
    missing_dates = expected.difference(present)
    longest = 0
    if len(missing_dates):
        runs = (missing_dates.to_series().diff() != pd.Timedelta(days=1)).cumsum()
        longest = int(runs.value_counts().max())
    return {
        "table": name,
        "expected_days": len(expected),
        "present_days": int(present.isin(expected).sum()),
        "missing_dates": len(missing_dates),
        "longest_missing_run_days": longest,
        "duplicate_dates": int(present.duplicated().sum()),
        "nan_counts": {c: int(df[c].isna().sum()) for c in df.columns if c != "date"},
        "first_date": str(present.min().date()) if len(present) else None,
        "last_date": str(present.max().date()) if len(present) else None,
    }


def validate_all(frames: dict[str, pd.DataFrame], start: str, end: str) -> dict:
    report: dict = {"tables": {}, "ok": True}
    for name, df in frames.items():
        _, failures = validate_frame(name, df)
        entry = completeness(name, df, start, end)
        entry["schema_failures"] = failures
        report["tables"][name] = entry
        if failures or entry["duplicate_dates"]:
            report["ok"] = False
    return report
