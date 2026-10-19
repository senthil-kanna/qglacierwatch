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
