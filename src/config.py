"""Project-wide settings. Change values here, not inside the scripts."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"

# Google Earth Engine project (noncommercial, no billing attached).
EE_PROJECT = os.getenv("EE_PROJECT", "ee-senthil-hydro")

# Gauge used as the basin outlet. Approximate coordinates of Beas at Bhuntar;
# replace with the exact India-WRIS station coordinates once confirmed.
GAUGE_NAME = "Beas_Bhuntar"
GAUGE_LON = 77.146
GAUGE_LAT = 31.877

# Observed CWC discharge for the Indus basin (incl. Beas) is classified and not on India-WRIS,
# so the target is GloFAS v4 reanalysis. This cell sits on the Beas main stem just below the
# Parvati confluence, matching the traced catchment.
GLOFAS_LAT = 31.825
GLOFAS_LON = 77.125

# HydroBASINS level used to trace the upstream catchment (8 = fine sub-basins).
HYBAS_LEVEL = 8

START_YEAR = 2015
END_YEAR = 2025

CONFIGS = ROOT / "configs"
ARTIFACTS = ROOT / "artifacts"

# "real" reads data/raw (Earth Engine + GloFAS). "demo" uses the clearly labelled synthetic
# fixture and never mixes with real outputs.
MODES = ("real", "demo")


def mode() -> str:
    m = os.getenv("QGW_MODE", "real")
    if m not in MODES:
        raise ValueError(f"QGW_MODE must be one of {MODES}, got {m!r}")
    return m


def data_root() -> Path:
    return Path(os.getenv("QGW_DATA", str(ROOT / "data")))


def raw_dir(m: str) -> Path:
    return data_root() / ("raw" if m == "real" else "synthetic")


def processed_dir(m: str) -> Path:
    return data_root() / "processed" / m


def artifact_dir(m: str) -> Path:
    return Path(os.getenv("QGW_ARTIFACTS", str(ARTIFACTS))) / m


def reports_dir(m: str) -> Path:
    return Path(os.getenv("QGW_REPORTS", str(ROOT / "reports"))) / m


def load_yaml(name: str) -> dict:
    import yaml

    with open(CONFIGS / f"{name}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
