"""Checksums and provenance manifest for raw inputs.

The manifest pins the SHA-256 of every raw file. Once recorded, a raw file is treated as
immutable: re-ingesting different bytes under the same name is reported as a conflict instead
of silently replacing the data a trained model was built on.

Usage:
    python -m src.ingest.provenance            # record or verify data/raw
    python -m src.ingest.provenance --mode demo
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from src import config

MANIFEST = "MANIFEST.json"

# Where each raw file comes from. Licences checked 2026-10; see docs/data_access.md.
SOURCES = {
    "modis_snow.parquet": {
        "product": "MODIS/061/MOD10A1 (NDSI_Snow_Cover) via Google Earth Engine",
        "licence": "NASA EOSDIS open data, no restrictions on reuse",
        "kind": "satellite observation, basin mean at 500 m",
    },
    "modis_snow_maps.parquet": {
        "product": "MODIS/061/MOD10A1 (NDSI_Snow_Cover) via Google Earth Engine",
        "licence": "NASA EOSDIS open data, no restrictions on reuse",
        "kind": "satellite observation, monthly snow-day frequency per 0.01 deg cell",
    },
    "era5_land.parquet": {
        "product": "ECMWF/ERA5_LAND/DAILY_AGGR via Google Earth Engine",
        "licence": "Copernicus licence (free, attribution required)",
        "kind": "reanalysis, basin mean at ~11 km",
    },
    "discharge.parquet": {
        "product": "GloFAS v4 river_discharge via Open-Meteo Flood API, or gauge CSV if supplied",
        "licence": "CC BY 4.0 (Copernicus Emergency Management Service)",
        "kind": "MODELLED discharge (seamless_v4: reanalysis to 2023-08-04, forecast-derived after) unless source column says 'gauge'",
    },
    "basin.geojson": {
        "product": "WWF HydroSHEDS HydroBASINS level 8, traced upstream of the outlet",
        "licence": "HydroSHEDS licence (free for non-commercial and commercial use with attribution)",
        "kind": "catchment polygon",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(raw: Path) -> dict:
    files = {}
    for p in sorted(raw.iterdir()):
        if p.is_file() and p.name not in (MANIFEST, "README.txt"):
            files[p.name] = {"sha256": sha256(p), "bytes": p.stat().st_size, **SOURCES.get(p.name, {})}
    return files


def record_or_verify(raw: Path) -> dict:
    """Write the manifest on first run; afterwards report files whose bytes changed."""
    current = build_manifest(raw)
    path = raw / MANIFEST
    if not path.exists():
        manifest = {"created_utc": datetime.now(UTC).isoformat(timespec="seconds"), "files": current}
        path.write_text(json.dumps(manifest, indent=2))
        return {"status": "recorded", "files": list(current), "conflicts": [], "new": []}

    manifest = json.loads(path.read_text())
    recorded = manifest["files"]
    conflicts = [n for n in current if n in recorded and recorded[n]["sha256"] != current[n]["sha256"]]
    new = [n for n in current if n not in recorded]
    if new:
        recorded.update({n: current[n] for n in new})
        path.write_text(json.dumps(manifest, indent=2))
    return {"status": "conflict" if conflicts else "verified", "files": list(current), "conflicts": conflicts, "new": new}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=config.mode(), choices=config.MODES)
    args = parser.parse_args()
    result = record_or_verify(config.raw_dir(args.mode))
    print(json.dumps(result, indent=2))
    if result["conflicts"]:
        raise SystemExit("Raw files changed since the manifest was recorded; move them to a new version.")


if __name__ == "__main__":
    main()
