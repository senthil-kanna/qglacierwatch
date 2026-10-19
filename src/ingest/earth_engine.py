"""Daily basin-average MODIS snow cover and ERA5-Land weather from Google Earth Engine.

Usage:
    python -m src.ingest.earth_engine            # all years in config
    python -m src.ingest.earth_engine --start 2024 --end 2024
"""

import argparse
import json

import ee
import pandas as pd

from src import config
from src.ingest.basin import basin_geometry
from src.ingest.ee_auth import initialize

MODIS_ID = "MODIS/061/MOD10A1"
ERA5_ID = "ECMWF/ERA5_LAND/DAILY_AGGR"
ERA5_BANDS = [
    "temperature_2m",
    "temperature_2m_min",
    "temperature_2m_max",
    "total_precipitation_sum",
    "snowfall_sum",
    "snowmelt_sum",
    "snow_depth_water_equivalent",
]


def _modis_stats(region: ee.Geometry):
    def per_image(img):
        # Clouds and other non-observations are masked in V6.1; fill them so they count as invalid.
        ndsi = img.select("NDSI_Snow_Cover").unmask(200)
        valid = ndsi.lte(100)
        snow = valid.And(ndsi.gte(10))
        stack = (
            valid.rename("valid_frac")
            .addBands(snow.rename("snow_frac_basin"))
            .addBands(ndsi.updateMask(valid).rename("ndsi_mean"))
        )
        stats = stack.reduceRegion(ee.Reducer.mean(), region, scale=500, maxPixels=1e9, tileScale=4)
        return ee.Feature(None, stats).set("date", img.date().format("YYYY-MM-dd"))

    return per_image


def _era5_stats(region: ee.Geometry):
    def per_image(img):
        stats = img.select(ERA5_BANDS).reduceRegion(
            ee.Reducer.mean(), region, scale=11132, maxPixels=1e9, tileScale=4
        )
        return ee.Feature(None, stats).set("date", img.date().format("YYYY-MM-dd"))

    return per_image


def _fetch_year(collection_id: str, mapper, year: int) -> pd.DataFrame:
    col = ee.ImageCollection(collection_id).filterDate(f"{year}-01-01", f"{year + 1}-01-01")
    feats = ee.FeatureCollection(col.map(mapper)).getInfo()["features"]
    df = pd.DataFrame([f["properties"] for f in feats])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")


def fetch_modis(region: ee.Geometry, years: range) -> pd.DataFrame:
    frames = [_fetch_year(MODIS_ID, _modis_stats(region), y) for y in years]
    df = pd.concat(frames, ignore_index=True)
    # Snow share of the cloud-free part of the basin; undefined when almost nothing is visible.
    df["snow_frac_valid"] = (df["snow_frac_basin"] / df["valid_frac"]).where(df["valid_frac"] >= 0.2)
    return df


def fetch_era5(region: ee.Geometry, years: range) -> pd.DataFrame:
    frames = [_fetch_year(ERA5_ID, _era5_stats(region), y) for y in years]
    df = pd.concat(frames, ignore_index=True)
    for col in ["temperature_2m", "temperature_2m_min", "temperature_2m_max"]:
        df[col] = df[col] - 273.15  # K -> degC
    for col in ["total_precipitation_sum", "snowfall_sum", "snowmelt_sum", "snow_depth_water_equivalent"]:
        df[col] = df[col] * 1000.0  # m -> mm
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=config.START_YEAR)
    parser.add_argument("--end", type=int, default=config.END_YEAR)
    args = parser.parse_args()
    years = range(args.start, args.end + 1)

    initialize()
    out = config.raw_dir("real")
    out.mkdir(parents=True, exist_ok=True)

    region = basin_geometry(config.GAUGE_LON, config.GAUGE_LAT, config.HYBAS_LEVEL)
    area_km2 = region.area(maxError=100).divide(1e6).getInfo()
    print(f"Basin {config.GAUGE_NAME}: {area_km2:,.0f} km2")
    (out / "basin.geojson").write_text(json.dumps(region.getInfo()))

    modis = fetch_modis(region, years)
    modis.to_parquet(out / "modis_snow.parquet", index=False)
    print(f"MODIS: {len(modis)} days, {modis['date'].min().date()} to {modis['date'].max().date()}")

    era5 = fetch_era5(region, years)
    era5.to_parquet(out / "era5_land.parquet", index=False)
    print(f"ERA5-Land: {len(era5)} days, {era5['date'].min().date()} to {era5['date'].max().date()}")


if __name__ == "__main__":
    main()
