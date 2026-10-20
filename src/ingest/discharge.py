"""Daily river discharge (target variable).

Primary source is a gauge CSV at data/raw/discharge_gauge.csv (columns: date, discharge_m3s),
used automatically if present. Otherwise GloFAS v4 is pulled from the Open-Meteo Flood API (free,
no key; data CC BY 4.0, Copernicus Emergency Management Service). The default `seamless_v4`
product at this cell is consolidated reanalysis up to 2023-08-04 and operational forecast-derived
from 2023-08-05; it also contains future seasonal-forecast values, so always cap the end date.

Usage:
    python -m src.ingest.discharge
"""

import pandas as pd
import requests

from src import config

FLOOD_API = "https://flood-api.open-meteo.com/v1/flood"
GAUGE_CSV = config.DATA_RAW / "discharge_gauge.csv"  # user-supplied gauge data always lives in data/raw


def fetch_glofas(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    params: dict[str, str | float] = {
        "latitude": lat,
        "longitude": lon,
        "daily": "river_discharge",
        "start_date": start,
        "end_date": end,
    }
    resp = requests.get(FLOOD_API, params=params, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    df = pd.DataFrame(
        {"date": pd.to_datetime(body["daily"]["time"]), "discharge_m3s": body["daily"]["river_discharge"]}
    )
    df["source"] = f"GloFAS_v4@{body['latitude']:.3f},{body['longitude']:.3f}"
    return df


def load_gauge(path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])[["date", "discharge_m3s"]]
    df["source"] = "gauge"
    return df


def main() -> None:
    start, end = f"{config.START_YEAR}-01-01", f"{config.END_YEAR}-12-31"
    if GAUGE_CSV.exists():
        df = load_gauge(GAUGE_CSV)
    else:
        df = fetch_glofas(config.GLOFAS_LAT, config.GLOFAS_LON, start, end)

    df = df[(df["date"] >= start) & (df["date"] <= end)].sort_values("date")
    out = config.raw_dir("real")
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "discharge.parquet", index=False)

    missing = df["discharge_m3s"].isna().sum()
    print(f"Discharge ({df['source'].iloc[0]}): {len(df)} days, {missing} missing, "
          f"mean {df['discharge_m3s'].mean():.1f} m3/s, max {df['discharge_m3s'].max():.1f} m3/s")


if __name__ == "__main__":
    main()
