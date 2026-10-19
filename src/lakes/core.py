"""Sensor-agnostic pieces of the lake pipeline (NumPy), mirrored by the Earth Engine code in gee.py.

Water rules
    optical:  NDWI = (G - NIR)/(G + NIR) > t_ndwi  AND  NIR < t_nir
              (snow and ice also have high NDWI/MNDWI but are bright in NIR; water is dark)
    sar:      VV backscatter (dB) < t_vv  (smooth open water is a specular reflector)
    fusion:   optical where a valid optical observation exists, otherwise SAR
Masks: cloud/cloud-shadow (s2cloudless + SCL), terrain shadow, slope > max_slope (lakes are flat),
SAR layover/shadow approximated by slope.

Metrics are estimated from a stratified pixel sample, so every count is weighted by
(class area / class sample size) to recover population-level confusion totals.
"""

import numpy as np
from scipy import stats


def optical_water(ndwi, nir, t_ndwi: float, t_nir: float):
    return (ndwi > t_ndwi) & (nir < t_nir)


def sar_water(vv_db, t_vv: float):
    return vv_db < t_vv


def fuse(optical, optical_valid, sar):
    return np.where(optical_valid, optical, sar)


def weighted_confusion(pred, label, weight) -> dict:
    pred, label, weight = np.asarray(pred, bool), np.asarray(label, bool), np.asarray(weight, float)
    return {
        "tp": float(weight[pred & label].sum()),
        "fp": float(weight[pred & ~label].sum()),
        "fn": float(weight[~pred & label].sum()),
        "tn": float(weight[~pred & ~label].sum()),
    }


def seg_metrics(c: dict) -> dict:
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    nan = float("nan")
    precision = tp / (tp + fp) if tp + fp else nan
    recall = tp / (tp + fn) if tp + fn else nan
    return {
        "iou": tp / (tp + fp + fn) if tp + fp + fn else nan,
        "dice_f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else nan,
        "precision": precision,
        "recall": recall,
        "area_error_frac": (fp - fn) / (tp + fn) if tp + fn else nan,  # (pred area - label area) / label area
    }


def strata_weights(label, area_by_class: dict) -> np.ndarray:
    """Weight = class area / number of sampled pixels of that class."""
    label = np.asarray(label, bool)
    n1, n0 = label.sum(), (~label).sum()
    return np.where(label, area_by_class[1] / max(n1, 1), area_by_class[0] / max(n0, 1))


def tune_thresholds(ndwi, nir, label, weight, ndwi_grid, nir_grid) -> tuple[float, float, float]:
    """Pick (t_ndwi, t_nir) maximising weighted F1 on the tuning sample."""
    best = (np.nan, np.nan, -1.0)
    for a in ndwi_grid:
        for b in nir_grid:
            f1 = seg_metrics(weighted_confusion(optical_water(ndwi, nir, a, b), label, weight))["dice_f1"]
            if np.isfinite(f1) and f1 > best[2]:
                best = (float(a), float(b), float(f1))
    return best


def tune_sar(vv, label, weight, vv_grid) -> tuple[float, float]:
    best = (np.nan, -1.0)
    for t in vv_grid:
        f1 = seg_metrics(weighted_confusion(sar_water(vv, t), label, weight))["dice_f1"]
        if np.isfinite(f1) and f1 > best[1]:
            best = (float(t), float(f1))
    return best


def block_split(block_ids, seed: int = 0, fractions=(0.5, 0.25, 0.25)) -> dict:
    """Assign spatial blocks to train/val/test so no block contributes to two splits."""
    ids = np.unique(block_ids)
    rng = np.random.default_rng(seed)
    rng.shuffle(ids)
    n_tr = int(round(fractions[0] * len(ids)))
    n_va = int(round(fractions[1] * len(ids)))
    return {int(b): ("train" if i < n_tr else "val" if i < n_tr + n_va else "test") for i, b in enumerate(ids)}


def comparable_years(valid_frac_by_year: dict, min_valid: float) -> list[int]:
    """Years whose composite observed at least min_valid of the lake zone."""
    return sorted(y for y, v in valid_frac_by_year.items() if v is not None and v >= min_valid)


def growth(years, areas, min_years: int = 5) -> dict:
    """Theil-Sen slope (km2/yr) with Kendall tau p-value; robust to single bad composites."""
    y, a = np.asarray(years, float), np.asarray(areas, float)
    ok = np.isfinite(a)
    y, a = y[ok], a[ok]
    if len(y) < min_years:
        return {"n_years": int(len(y)), "slope_km2_per_yr": None, "rel_change_per_yr": None, "kendall_p": None}
    slope, intercept, lo, hi = stats.theilslopes(a, y)
    tau = stats.kendalltau(y, a)
    base = np.median(a[: max(2, len(a) // 3)])
    return {
        "n_years": int(len(y)),
        "slope_km2_per_yr": float(slope),
        "slope_ci95": [float(lo), float(hi)],
        "rel_change_per_yr": float(slope / base) if base > 0 else None,
        "kendall_p": float(tau.pvalue),
    }
