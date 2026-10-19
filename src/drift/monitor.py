"""Drift monitors: data quality, covariate, prediction and residual drift.

Two covariate detectors share identical multiple-testing, persistence and severity rules and differ
only in their reference distribution:

- baseline:      two-sample KS test of daily values in the current window against the previous
                 365 days, ignoring season. Expected to fire at every monsoon/melt transition.
- season-aware:  the current window mean is compared with the means of the same calendar window in
                 each past year (one value per year). Under "no drift" the current mean is another
                 draw from that between-year distribution, so z = (m - mean_ref) / (sd_ref * sqrt(1+1/n))
                 is referred to Student's t with n-1 df (a prediction interval). Using window means of
                 whole years absorbs within-window autocorrelation and year-to-year variability.

Residual drift compares the recent verified forecast QS and P10-P90 coverage with out-of-sample
residuals from the same part of the year. Observations arrive with a lag, so only target dates that
are already verifiable at the check date enter the window.
"""

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from src.evaluate.metrics import quantile_score


@dataclass
class Finding:
    check_date: str
    kind: str          # data_quality | pipeline | covariate | prediction | residual
    detector: str      # baseline | season_aware | rule
    target: str        # feature name, horizon or source
    statistic: float
    p_value: float | None
    flagged: bool
    detail: dict = field(default_factory=dict)


def bh_reject(pvals: list[float], q: float) -> list[bool]:
    """Benjamini-Hochberg step-up; NaN p-values are never rejected."""
    p = np.asarray(pvals, float)
    ok = np.isfinite(p)
    reject = np.zeros(len(p), bool)
    if not ok.any():
        return reject.tolist()
    idx = np.where(ok)[0]
    order = idx[np.argsort(p[idx])]
    m = len(order)
    thresh = q * np.arange(1, m + 1) / m
    passed = p[order] <= thresh
    if passed.any():
        k = np.max(np.where(passed)[0])
        reject[order[: k + 1]] = True
    return reject.tolist()


def _same_window_in_year(T: pd.Timestamp, year: int, window: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    day = min(T.day, 28) if T.month == 2 else T.day
    end = pd.Timestamp(year=year, month=T.month, day=day)
    return end - pd.Timedelta(days=window - 1), end


def _window_mean(s: pd.Series, start, end, min_valid: float) -> float:
    w = s.loc[start:end]
    expected = (end - start).days + 1
    if w.notna().sum() < min_valid * expected:
        return float("nan")
    return float(w.mean())


def season_aware_test(s: pd.Series, T: pd.Timestamp, cfg: dict) -> tuple[float, float, dict]:
    W, mv = cfg["window_days"], cfg["min_window_valid_frac"]
    cur = _window_mean(s, T - pd.Timedelta(days=W - 1), T, mv)
    first_year = s.first_valid_index().year if s.first_valid_index() is not None else T.year
    years = [y for y in range(T.year - cfg["covariate"]["max_reference_years"], T.year) if y >= first_year]
    ref = []
    for y in years:
        a, b = _same_window_in_year(T, y, W)
        if a < s.index.min():
            continue
        m = _window_mean(s, a, b, mv)
        if np.isfinite(m):
            ref.append(m)
    n = len(ref)
    detail = {"current_mean": cur, "n_reference_years": n}
    if not np.isfinite(cur) or n < cfg["covariate"]["min_reference_years"]:
        return float("nan"), float("nan"), {**detail, "status": "insufficient_data"}
    mu, sd = float(np.mean(ref)), float(np.std(ref, ddof=1))
    if sd == 0:
        return float("nan"), float("nan"), {**detail, "status": "zero_reference_variance"}
    z = (cur - mu) / (sd * np.sqrt(1 + 1 / n))
    p = float(2 * stats.t.sf(abs(z), df=n - 1))
    return float(z), p, {**detail, "reference_mean": mu, "reference_sd": sd}


def baseline_test(s: pd.Series, T: pd.Timestamp, cfg: dict) -> tuple[float, float, dict]:
    W = cfg["window_days"]
    cur = s.loc[T - pd.Timedelta(days=W - 1) : T].dropna()
    ref = s.loc[T - pd.Timedelta(days=W + cfg["covariate"]["baseline_reference_days"] - 1) : T - pd.Timedelta(days=W)].dropna()
    if len(cur) < cfg["min_window_valid_frac"] * W or len(ref) < 0.5 * cfg["covariate"]["baseline_reference_days"]:
        return float("nan"), float("nan"), {"status": "insufficient_data"}
    r = stats.ks_2samp(cur, ref)
    return float(r.statistic), float(r.pvalue), {"n_current": len(cur), "n_reference": len(ref)}


def covariate_checks(table: pd.DataFrame, T: pd.Timestamp, cfg: dict, columns: list[str], kind: str) -> list[Finding]:
    out = []
    for detector, fn in (("baseline", baseline_test), ("season_aware", season_aware_test)):
        res = [(c, *fn(table[c], T, cfg)) for c in columns]
        flags = bh_reject([r[2] for r in res], cfg["covariate"]["fdr_q"])
        for (c, stat, p, detail), f in zip(res, flags, strict=True):
            out.append(Finding(str(T.date()), kind, detector, c, stat, p, bool(f), detail))
    return out


def data_quality_checks(table: pd.DataFrame, daily: pd.DataFrame, T: pd.Timestamp, cfg: dict) -> list[Finding]:
    W = cfg["window_days"]
    win = table.loc[T - pd.Timedelta(days=W - 1) : T]
    out = []
    dq = cfg["data_quality"]
    for src, col in (("discharge", "flag_q_missing"), ("era5", "flag_era5_missing"), ("modis", "flag_modis_missing")):
        frac = float(win[col].mean()) if len(win) else 1.0
        out.append(Finding(str(T.date()), "data_quality", "rule", src, frac, None, frac > dq["max_missing_frac"][src], {"missing_frac": frac}))
    # Sensor or pipeline failure: a continuous variable repeating the same value for days.
    dwin = daily.loc[T - pd.Timedelta(days=W - 1) : T]
    for col in ("temperature_2m", "discharge_m3s", "snow_frac_valid"):
        s = dwin[col].dropna()
        if col == "snow_frac_valid":
            s = s[s > 0]  # a genuinely snow-free basin is legitimately constant at 0
        run = int((s.diff() == 0).astype(int).groupby((s.diff() != 0).cumsum()).sum().max()) + 1 if len(s) > 1 else 0
        out.append(Finding(str(T.date()), "pipeline", "rule", col, run, None, run >= dq["stuck_days"], {"longest_constant_run_days": run}))
    return out


def residual_checks(preds: pd.DataFrame, T: pd.Timestamp, cfg: dict, discharge_lag: int = 1) -> list[Finding]:
    """preds: out-of-sample forecasts with columns target_date, h, obs, p10, p50, p90."""
    rc = cfg["residual"]
    out = []
    latest_verifiable = T - pd.Timedelta(days=discharge_lag)
    start = latest_verifiable - pd.Timedelta(days=cfg["window_days"] - 1)
    for h in rc["horizons"]:
        p = preds[(preds["h"] == h) & preds["obs"].notna()]
        cur = p[(p["target_date"] >= start) & (p["target_date"] <= latest_verifiable)]
        past = p[p["target_date"] < start]
        if len(cur) < rc["min_window_samples"]:
            for det in ("baseline", "season_aware"):
                out.append(Finding(str(T.date()), "residual", det, f"h{h}", float("nan"), None, False, {"status": "insufficient_window", "n": len(cur)}))
            continue
        qcur = quantile_score(cur["obs"], cur[["p10", "p50", "p90"]].to_numpy())
        cov = float(np.mean((cur["obs"] >= cur["p10"]) & (cur["obs"] <= cur["p90"])))
        k = int(np.sum((cur["obs"] >= cur["p10"]) & (cur["obs"] <= cur["p90"])))
        p_cov = float(stats.binomtest(k, len(cur), 0.8, alternative="less").pvalue)

        doy_cur = np.unique(cur["target_date"].dt.dayofyear.to_numpy())
        dpast = past["target_date"].dt.dayofyear.to_numpy()
        diff = np.abs(dpast[:, None] - doy_cur[None, :])
        circ = np.minimum(diff, 366 - diff).min(axis=1)  # circular distance to the nearest window day
        refs = {"baseline": past, "season_aware": past[circ <= rc["doy_halfwidth"]]}
        for det, ref in refs.items():
            if len(ref) < rc["min_reference_samples"]:
                out.append(Finding(str(T.date()), "residual", det, f"h{h}", float("nan"), None, False, {"status": "insufficient_reference", "n_ref": len(ref)}))
                continue
            qref = quantile_score(ref["obs"], ref[["p10", "p50", "p90"]].to_numpy())
            ratio = float(qcur.mean() / qref.mean())
            flagged = ratio > rc["qs_ratio_alert"] or p_cov < rc["coverage_p_alert"]
            out.append(
                Finding(
                    str(T.date()), "residual", det, f"h{h}", ratio, p_cov, bool(flagged),
                    {"qs_window": float(qcur.mean()), "qs_reference": float(qref.mean()), "coverage_window": cov, "n": len(cur), "n_ref": len(ref)},
                )
            )
    return out


def apply_persistence(findings: pd.DataFrame, k_cov: int, k_res: int) -> pd.DataFrame:
    """An alert fires when the same (kind, detector, target) is flagged in k consecutive checks."""
    findings = findings.sort_values("check_date").copy()
    findings["alert"] = False
    for (kind, _, _), g in findings.groupby(["kind", "detector", "target"]):
        k = {"covariate": k_cov, "prediction": k_cov, "residual": k_res}.get(kind, 1)
        run = g["flagged"].astype(int).groupby((~g["flagged"]).cumsum()).cumsum()
        findings.loc[g.index, "alert"] = run >= k
    return findings


def severity(alerts_at_check: pd.DataFrame) -> str:
    if alerts_at_check.empty:
        return "none"
    kinds = set(alerts_at_check["kind"])
    if "pipeline" in kinds or ("residual" in kinds and "covariate" in kinds):
        return "critical"
    if "residual" in kinds or (alerts_at_check["kind"] == "covariate").sum() >= 3 or "data_quality" in kinds:
        return "warning"
    return "info"


def to_frame(findings: list[Finding]) -> pd.DataFrame:
    return pd.DataFrame([asdict(f) for f in findings])
