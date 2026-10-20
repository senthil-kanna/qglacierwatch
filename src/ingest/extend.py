"""Create a new raw-data version: byte-identical copies of the recorded raw files plus appended days.

Keeps every recorded value unchanged (no re-download of past years, whose upstream values can be
revised), appends only dates after the last recorded day up to --until, and records what was
done in extend_log.json. Used for the registered fresh 2026 evaluation (docs/protocol_fresh2026.md).

Usage (destination = QGW_DATA/raw, source = data/raw):
    QGW_DATA=data/fresh2026 python -m src.ingest.extend --until 2026-09-30
"""

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src import config
from src.ingest.provenance import MANIFEST, sha256

FILES = ("basin.geojson", "modis_snow.parquet", "era5_land.parquet", "discharge.parquet")


def append_rows(old: pd.DataFrame, new: pd.DataFrame, until: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """Append rows strictly after the last old date and up to `until`; same columns, no duplicates."""
    last = old["date"].max()
    add = new[(new["date"] > last) & (new["date"] <= until)].sort_values("date")
    missing_cols = set(old.columns) - set(add.columns)
    if missing_cols:
        raise ValueError(f"new rows lack columns {sorted(missing_cols)}")
    out = pd.concat([old, add[old.columns]], ignore_index=True)
    if out["date"].duplicated().any() or not out["date"].is_monotonic_increasing:
        raise ValueError("dates must be unique and increasing after append")
    expected = pd.date_range(last + pd.Timedelta(days=1), until, freq="D")
    gaps = expected.difference(pd.DatetimeIndex(add["date"]))
    info = {"appended_from": str(add["date"].min().date()) if len(add) else None, "appended_to": str(add["date"].max().date()) if len(add) else None,
            "rows_added": int(len(add)), "missing_dates": [str(d.date()) for d in gaps]}
    return out, info


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--until", required=True, help="last date to append (YYYY-MM-DD)")
    p.add_argument("--source", default=str(config.ROOT / "data" / "raw"))
    args = p.parse_args()
    until = pd.Timestamp(args.until)
    src, dst = Path(args.source).resolve(), config.raw_dir("real").resolve()
    if src == dst:
        raise SystemExit("Destination equals source; set QGW_DATA to a new data-version root.")
    manifest = json.loads((src / MANIFEST).read_text())["files"]
    dst.mkdir(parents=True, exist_ok=True)
    log: dict = {"created_utc": datetime.now(UTC).isoformat(timespec="seconds"), "source": str(src), "until": args.until, "files": {}}

    for name in FILES:
        h = sha256(src / name)
        if manifest[name]["sha256"] != h:
            raise SystemExit(f"{name} differs from the recorded manifest; refusing to build a version on unrecorded data.")
        shutil.copy2(src / name, dst / name)
        log["files"][name] = {"source_sha256": h}

    # Late imports: Earth Engine only when actually fetching.
    import ee

    from src.ingest.discharge import fetch_glofas
    from src.ingest.earth_engine import fetch_era5, fetch_modis
    from src.ingest.ee_auth import initialize

    initialize()
    region = ee.Geometry(json.loads((dst / "basin.geojson").read_text()))
    for name, fetch in (("modis_snow.parquet", fetch_modis), ("era5_land.parquet", fetch_era5)):
        old = pd.read_parquet(dst / name)
        years = range(old["date"].max().year, until.year + 1)
        merged, info = append_rows(old, fetch(region, years), until)
        merged.to_parquet(dst / name, index=False)
        log["files"][name].update(info)
        print(f"{name}: +{info['rows_added']} rows {info['appended_from']}..{info['appended_to']}, missing {len(info['missing_dates'])}")

    old = pd.read_parquet(dst / "discharge.parquet")
    if (old["source"] == "gauge").any():
        raise SystemExit("Gauge discharge present; extend it from the gauge CSV instead.")
    start = old["date"].max() + pd.Timedelta(days=1)
    new = fetch_glofas(config.GLOFAS_LAT, config.GLOFAS_LON, str(start.date()), str(until.date()))
    if set(new["source"]) != set(old["source"]):
        raise SystemExit(f"GloFAS cell changed: {set(new['source'])} vs {set(old['source'])}")
    merged, info = append_rows(old, new, until)
    merged.to_parquet(dst / "discharge.parquet", index=False)
    # Stability check (reported only): does the provider still serve the stored last year unchanged?
    y = old["date"].max().year
    again = fetch_glofas(config.GLOFAS_LAT, config.GLOFAS_LON, f"{y}-01-01", f"{y}-12-31").set_index("date")["discharge_m3s"]
    stored = old.set_index("date")["discharge_m3s"].loc[f"{y}-01-01":f"{y}-12-31"]
    diff = (again.reindex(stored.index) - stored).abs()
    info["stability_check"] = {"year": y, "days": int(len(stored)), "days_changed_upstream": int((diff > 1e-6).sum()), "max_abs_change_m3s": float(diff.max())}
    info["product_note"] = "Open-Meteo seamless_v4: consolidated reanalysis to 2023-08-04, forecast-derived from 2023-08-05 (docs/protocol_fresh2026.md)"
    log["files"]["discharge.parquet"].update(info)
    print(f"discharge.parquet: +{info['rows_added']} rows {info['appended_from']}..{info['appended_to']}, missing {len(info['missing_dates'])}; "
          f"stability {y}: {info['stability_check']['days_changed_upstream']} of {len(stored)} days changed upstream")
    (dst / "extend_log.json").write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
