"""Write the two SYNTHETIC sample files for the dashboard's "Upload and check" (dashboard/samples/).

Both start from the real archive for 1 Jun - 31 Jul 2025 (ERA5-Land temperature and precipitation,
MODIS snow fraction with cloud gaps interpolated, GloFAS discharge) and are then altered with a fixed seed:

    normal_data.csv   small noise only (temperature +-0.2 deg C, discharge +-1 %)
    changed_data.csv  3 deg C warmer, and discharge 60 % higher with +-30 % pulses every 6 days
                      (the kind of change an upstream release or a rating-curve shift would cause)

Neither file is an observation. Usage:  python scripts/make_upload_samples.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.features.build import load_raw, merge_daily  # noqa: E402

OUT = ROOT / "dashboard" / "samples"
START, END = "2025-06-01", "2025-07-31"
SEED = 2025


def base() -> pd.DataFrame:
    d = merge_daily(load_raw("real"), START, END)
    return pd.DataFrame(
        {
            "date": d.index.strftime("%Y-%m-%d"),
            "temperature_2m": d["temperature_2m"].to_numpy(),
            "precipitation": d["total_precipitation_sum"].to_numpy(),
            "snow_frac": d["snow_frac_valid"].interpolate(limit_direction="both").to_numpy(),
            "discharge": d["discharge_m3s"].to_numpy(),
        }
    )


def write(df: pd.DataFrame, name: str, note: str) -> None:
    df = df.round({"temperature_2m": 2, "precipitation": 2, "snow_frac": 3, "discharge": 1})
    path = OUT / name
    with path.open("w", newline="") as fh:
        fh.write(f"# SYNTHETIC sample for the QGlacierWatch drift demo, not an observation. {note}\n")
        df.to_csv(fh, index=False)
    print(f"wrote {path.relative_to(ROOT)} ({len(df)} days)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    b = base()
    n = len(b)

    normal = b.copy()
    normal["temperature_2m"] += rng.normal(0, 0.2, n)
    normal["discharge"] *= 1 + rng.normal(0, 0.01, n)
    write(normal, "normal_data.csv", f"Archive {START}..{END} with small noise only.")

    changed = b.copy()
    changed["temperature_2m"] += 3.0
    changed["discharge"] *= 1.6 * (1 + 0.3 * np.sin(2 * np.pi * np.arange(n) / 6))
    write(changed, "changed_data.csv", f"Archive {START}..{END}, 3 deg C warmer, discharge x1.6 with 6-day pulses.")


if __name__ == "__main__":
    main()
