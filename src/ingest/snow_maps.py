"""Monthly MODIS snow-cover frequency maps over the basin, for the dashboard map.

For each month and grid cell (0.01 deg, about 1 km), snow frequency = snow days / cloud-free days,
using the same rule as the basin series (MOD10A1 v6.1, NDSI_Snow_Cover >= 10). Cells with fewer
than MIN_VALID_DAYS cloud-free days in the month are left empty.

Usage:
    python -m src.ingest.snow_maps                 # all years in config
    python -m src.ingest.snow_maps --start 2024 --end 2024
"""

import argparse
import json

import ee
import numpy as np
import pandas as pd

from src import config
from src.ingest.earth_engine import MODIS_ID
from src.ingest.ee_auth import initialize

CELL_DEG = 0.01
MIN_VALID_DAYS = 3
OUT_NAME = "modis_snow_maps.parquet"


def month_bands(year: int, month: int) -> ee.Image:
    start = ee.Date.fromYMD(year, month, 1)
    col = ee.ImageCollection(MODIS_ID).filterDate(start, start.advance(1, "month")).select("NDSI_Snow_Cover")

    def flags(img):
        ndsi = img.unmask(200)
        valid = ndsi.lte(100)
        return valid.rename("valid").addBands(valid.And(ndsi.gte(10)).rename("snow"))

    s = col.map(flags).sum()
    freq = s.select("snow").divide(s.select("valid")).updateMask(s.select("valid").gte(MIN_VALID_DAYS))
    return freq.unmask(-1).rename(f"f{month:02d}").addBands(s.select("valid").rename(f"v{month:02d}"))


def fetch_year(year: int, basin: ee.Geometry, bounds: tuple[float, float, float, float]) -> pd.DataFrame:
    x0, y0, x1, y1 = bounds
    w, h = int(np.ceil((x1 - x0) / CELL_DEG)), int(np.ceil((y1 - y0) / CELL_DEG))
    inside = ee.Image(0).byte().paint(basin, 1).rename("inside")
    img = ee.Image.cat([inside] + [month_bands(year, m) for m in range(1, 13)]).toFloat()
    arr = ee.data.computePixels({
        "expression": img,
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": w, "height": h},
            "affineTransform": {"scaleX": CELL_DEG, "shearX": 0, "translateX": x0, "shearY": 0, "scaleY": -CELL_DEG, "translateY": y1},
            "crsCode": "EPSG:4326",
        },
    })
    rows, cols = np.nonzero(arr["inside"] > 0)
    lon = x0 + (cols + 0.5) * CELL_DEG
    lat = y1 - (rows + 0.5) * CELL_DEG
    frames = []
    for m in range(1, 13):
        f = arr[f"f{m:02d}"][rows, cols].astype(float)
        frames.append(pd.DataFrame({
            "year": year, "month": m, "lon": lon.round(4), "lat": lat.round(4),
            "snow_freq": np.where(f < 0, np.nan, f), "valid_days": arr[f"v{m:02d}"][rows, cols].astype(int),
        }))
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=config.START_YEAR)
    parser.add_argument("--end", type=int, default=config.END_YEAR)
    args = parser.parse_args()

    initialize()
    out = config.raw_dir("real")
    gj = json.loads((out / "basin.geojson").read_text())
    basin = ee.Geometry(gj)
    c = np.array(gj["coordinates"][0])
    bounds = (np.floor(c[:, 0].min() / CELL_DEG) * CELL_DEG, np.floor(c[:, 1].min() / CELL_DEG) * CELL_DEG, c[:, 0].max(), c[:, 1].max())

    frames = []
    for y in range(args.start, args.end + 1):
        frames.append(fetch_year(y, basin, bounds))
        print(f"  {y}: {frames[-1]['snow_freq'].notna().mean():.0%} of cell-months observed", flush=True)
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(out / OUT_NAME, index=False)
    print(f"Snow maps: {df[['lon', 'lat']].drop_duplicates().shape[0]} cells x {len(df) // max(1, df[['lon', 'lat']].drop_duplicates().shape[0])} months -> {out / OUT_NAME}")


if __name__ == "__main__":
    main()
