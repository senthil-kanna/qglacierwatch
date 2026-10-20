"""Consistency check of GloFAS and forecasts against Bajoura Bridge telemetry (docs/protocol_gauge_check.md).

Raw NWDP files are read from git-ignored data/external/nwdp_hp_discharge/ and never modified;
only aggregate metrics are written (reports/real/gauge_check.{json,md}). Nothing is retrained.

Usage:
    python -m src.evaluate.gauge_check
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src import config
from src.evaluate.metrics import kge, mae, nse, score_all, season_of

STATION = "Bajoura Bridge"
SRC = config.ROOT / "data" / "external" / "nwdp_hp_discharge"
FILES = ["river_discharge_tele_hr_himachal_pradesh_hp_1970_2025.csv", "river_discharge_tele_hr_himachal_pradesh_hp_2026_2030.csv"]
MIN_READINGS = 48
MIN_SEASON_N = 30
ACK = "Data: Himachal Pradesh Water Department, via National Water Data Portal (NWIC, Ministry of Jal Shakti)."


def load_readings(paths: list[Path], station: str = STATION) -> pd.DataFrame:
    """Readings with UTC timestamps (source times assumed IST); invalid values set to NaN."""
    frames = []
    for p in paths:
        df = pd.read_csv(p, low_memory=False)
        df = df[df["Station"] == station]
        col = next(c for c in df.columns if "Discharge" in c)
        frames.append(pd.DataFrame({"t_local": pd.to_datetime(df["Data Acquisition Time"], format="%d-%m-%Y %H:%M"),
                                    "v": pd.to_numeric(df[col], errors="coerce")}))
    r = pd.concat(frames, ignore_index=True).sort_values("t_local", kind="stable")
    r["v"] = r["v"].where(r["v"] >= 0)
    r["t"] = r["t_local"] - pd.Timedelta(hours=5, minutes=30)
    return r


def flag_readings(r: pd.DataFrame) -> pd.DataFrame:
    """Reading-level flags: zero, isolated spike (> 3x the +/-2 h median and > 50 m3/s above), flatline (>= 24 equal in a row)."""
    r = r.drop_duplicates("t", keep="first").set_index("t").sort_index()
    v = r["v"]
    med = v.rolling("4h", center=True, min_periods=3).median()
    r["zero"] = v == 0
    r["spike"] = (v > 3 * med) & (v - med > 50)
    run = (v != v.shift()).cumsum()
    r["flatline"] = v.notna() & (v.groupby(run).transform("size") >= 24)
    return r


def daily_means(r: pd.DataFrame, min_readings: int = MIN_READINGS) -> pd.DataFrame:
    g = r.groupby(r.index.floor("D"))
    d = pd.DataFrame({"n": g["v"].count(), "obs": g["v"].mean(), "zero": g["zero"].any(), "spike": g["spike"].any(), "flatline": g["flatline"].any()})
    d = d[d["n"] >= min_readings].copy()
    d["extreme"] = d["obs"] > d["obs"].quantile(0.995)
    d["flagged"] = d[["zero", "spike", "flatline", "extreme"]].any(axis=1)
    d.index.name = "date"
    return d


def pair_metrics(o: pd.Series, s: pd.Series) -> dict:
    ok = o.notna() & s.notna()
    o, s = o[ok], s[ok]
    if len(o) == 0:
        return {"n": 0}
    return {"n": int(len(o)), "obs_mean": float(o.mean()), "sim_mean": float(s.mean()), "bias_ratio": float(s.mean() / o.mean()),
            "median_ratio": float(np.median(s[o > 0] / o[o > 0])), "r": float(np.corrcoef(o, s)[0, 1]) if len(o) > 2 else None,
            "nse": nse(o, s), "kge": kge(o, s), "mae": mae(o, s)}


def by_season(idx: pd.DatetimeIndex, fn, seasons: dict) -> dict:
    lab = season_of(idx, seasons)
    out = {}
    for s in seasons:
        m = lab == s
        out[s] = fn(m) if m.sum() >= MIN_SEASON_N else {"n": int(m.sum()), "note": "insufficient"}
    return out


def glofas_check(daily: pd.DataFrame, glofas: pd.Series, seasons: dict) -> dict:
    j = daily[["obs", "flagged"]].join(glofas.rename("glofas"), how="inner").dropna(subset=["obs", "glofas"])
    out: dict[str, Any] = {}
    for name, part in (("all", j), ("unflagged", j[~j["flagged"]]), ("2023_2025", j.loc[:"2025-12-31"]), ("2026", j.loc["2026-01-01":])):
        out[name] = {"overall": pair_metrics(part["obs"], part["glofas"]),
                     "seasons": by_season(part.index, lambda m, p=part: pair_metrics(p["obs"][m], p["glofas"][m]), seasons)}
    out["period"] = [str(j.index.min().date()), str(j.index.max().date())]
    return out


def forecast_check(hind: pd.DataFrame, daily: pd.DataFrame, seasons: dict) -> dict:
    t = hind[hind["split"] == "test"].join(daily[["obs", "flagged"]].rename(columns={"obs": "gauge"}), on="target_date", how="inner")
    out = {}
    for (model, h), g in t.groupby(["model", "h"]):
        q = g[["p10", "p50", "p90"]].to_numpy()
        key = f"{model}|h{h}"
        out[key] = {"vs_gauge": score_all(g["gauge"], q), "vs_glofas_same_dates": score_all(g["obs"], q),
                    "vs_gauge_unflagged": score_all(g.loc[~g["flagged"], "gauge"], q[~g["flagged"].to_numpy()]),
                    "seasons_vs_gauge": by_season(pd.DatetimeIndex(g["target_date"]), lambda m, g=g, q=q: score_all(g["gauge"].to_numpy()[m], q[m]), seasons)}
    return out


def fmt(x, nd=2):
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def markdown(rep: dict) -> str:
    q = rep["quality"]
    L = [f"# Gauge check: Bajoura Bridge (generated {rep['generated_utc']})", "", ACK, "",
         "Consistency check against a state telemetry gauge, not independent validation: method, rating curve and quality control are unknown "
         "(`docs/protocol_gauge_check.md`). Bajoura is 3.7 km downstream of the catchment outlet. Raw data are not redistributed.", "",
         f"Readings: {q['readings']:,} ({q['invalid']:,} invalid, {q['duplicates']} duplicate timestamps). Valid days (>= {MIN_READINGS} readings): "
         f"{q['valid_days']} of {q['calendar_days']} calendar days {q['first_day']}..{q['last_day']}. Flagged days: zero {q['flags']['zero']}, "
         f"spike {q['flags']['spike']}, flatline {q['flags']['flatline']}, extreme {q['flags']['extreme']} ({', '.join(q['extreme_days'])}).", "",
         "## C1 GloFAS vs observed (daily)", "", "| subset | n | obs mean | GloFAS mean | bias ratio | median ratio | r | NSE | KGE |", "|---|---|---|---|---|---|---|---|---|"]
    for k in ("all", "unflagged", "2023_2025", "2026"):
        m = rep["glofas"][k]["overall"]
        L.append(f"| {k} | {m['n']} | {fmt(m.get('obs_mean'), 1)} | {fmt(m.get('sim_mean'), 1)} | {fmt(m.get('bias_ratio'))} | {fmt(m.get('median_ratio'))} | "
                 f"{fmt(m.get('r'))} | {fmt(m.get('nse'))} | {fmt(m.get('kge'))} |")
    L += ["", "| season (all days) | n | bias ratio | median ratio | r | NSE |", "|---|---|---|---|---|---|"]
    for s, m in rep["glofas"]["all"]["seasons"].items():
        L.append(f"| {s} | {m['n']} | {fmt(m.get('bias_ratio'))} | {fmt(m.get('median_ratio'))} | {fmt(m.get('r'))} | {fmt(m.get('nse'))} |")
    for name, key in (("C2a Original forecasts (test 2023-2025)", "forecasts_original"), ("C2b Fresh 2026 forecasts (test Jan-Sep 2026)", "forecasts_2026")):
        L += ["", f"## {name}", "", "| model | h | n | NSE vs gauge | KGE vs gauge | QS vs gauge | cov80 vs gauge | NSE vs GloFAS (same dates) | cov80 vs GloFAS |",
              "|---|---|---|---|---|---|---|---|---|"]
        for k, v in rep[key].items():
            a, b = v["vs_gauge"], v["vs_glofas_same_dates"]
            model, h = k.split("|")
            L.append(f"| {model} | {h[1:]} | {a['n']} | {fmt(a['nse'])} | {fmt(a['kge'])} | {fmt(a['qs'])} | {fmt(a['coverage_80'])} | {fmt(b['nse'])} | {fmt(b['coverage_80'])} |")
    return "\n".join(L) + "\n"


def main() -> None:
    argparse.ArgumentParser().parse_args()
    paths = [SRC / f for f in FILES]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise SystemExit(f"Missing gauge files {missing} in {SRC}; see docs/protocol_gauge_check.md.")
    seasons = config.load_yaml("forecast")["seasons"]
    raw = load_readings(paths)
    flagged = flag_readings(raw)
    daily = daily_means(flagged)
    glofas = pd.read_parquet(config.ROOT / "data" / "fresh2026" / "raw" / "discharge.parquet").set_index("date")["discharge_m3s"]
    cal = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    rep = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"), "acknowledgement": ACK, "station": STATION,
        "quality": {"readings": int(len(raw)), "invalid": int(raw["v"].isna().sum()), "duplicates": int(raw["t"].duplicated().sum()),
                    "valid_days": int(len(daily)), "calendar_days": int(len(cal)), "first_day": str(cal.min().date()), "last_day": str(cal.max().date()),
                    "valid_days_per_month": {str(k): int(v) for k, v in daily.groupby(daily.index.to_period("M")).size().items()},
                    "flags": {f: int(daily[f].sum()) for f in ("zero", "spike", "flatline", "extreme")},
                    "extreme_days": [f"{d.date()} ({v:.0f})" for d, v in daily.loc[daily["extreme"], "obs"].items()]},
        "glofas": glofas_check(daily, glofas, seasons),
        "forecasts_original": forecast_check(pd.read_parquet(config.ROOT / "artifacts" / "real" / "hindcasts.parquet"), daily, seasons),
        "forecasts_2026": forecast_check(pd.read_parquet(config.ROOT / "artifacts" / "fresh2026" / "real" / "hindcasts.parquet"), daily, seasons),
    }
    out = config.ROOT / "reports" / "real"
    (out / "gauge_check.json").write_text(json.dumps(rep, indent=2, default=float))
    (out / "gauge_check.md").write_text(markdown(rep), encoding="utf-8")
    print(markdown(rep))


if __name__ == "__main__":
    main()
