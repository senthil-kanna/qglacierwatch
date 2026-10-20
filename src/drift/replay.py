"""Historical replay of the drift monitors and controlled synthetic-perturbation evaluation.

Replay: weekly checks over the whole record. Covariate checks need >= 4 past years of the same
calendar window, so the season-aware detector starts in 2019. Residual checks need out-of-sample
forecasts, which exist only for the calibration and test periods (2021 onward).

Synthetic evaluation: known perturbations (sensor bias, sensor dropout, rating-curve shift) are
injected into copies of the real inputs at random onsets. These are SYNTHETIC events, never real
climate events. Detection delay, misses, false alarms, precision and recall are measured for both
detectors under identical persistence and FDR rules.

Usage:
    python -m src.drift.replay                    # replay + synthetic evaluation
    python -m src.drift.replay --latest           # one operational check at the newest data
"""

import argparse
import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from src import config
from src.drift.monitor import (
    apply_persistence,
    covariate_checks,
    data_quality_checks,
    residual_checks,
    severity,
    to_frame,
)
from src.drift.policy import recommend
from src.features.build import build_features, load_latest, load_raw, merge_daily


def run_checks(table, daily, preds, dates, cfg, lags) -> pd.DataFrame:
    findings = []
    p50 = None
    if preds is not None and not preds.empty:
        p50 = preds[preds["h"] == 7].set_index("issue_date")["p50"].pipe(np.log).rename("log_p50_h7")
        p50 = p50.reindex(table.index)
    for T in dates:
        findings += data_quality_checks(table, daily, T, cfg)
        findings += covariate_checks(table, T, cfg, cfg["covariate"]["features"], "covariate")
        if p50 is not None:
            findings += [f for f in covariate_checks(pd.DataFrame({"log_p50_h7": p50}), T, cfg, ["log_p50_h7"], "prediction")]
            findings += residual_checks(preds, T, cfg, lags["discharge"])
    df = to_frame(findings)
    return apply_persistence(df, cfg["covariate"]["persistence_checks"], cfg["residual"]["persistence_checks"])


def out_of_sample(mode: str) -> tuple[pd.DataFrame | None, str | None]:
    path = config.artifact_dir(mode) / "hindcasts.parquet"
    res = config.reports_dir(mode) / "forecast_results.json"
    if not path.exists() or not res.exists():
        return None, None
    family = json.loads(res.read_text())["meta"]["best_learned_model"]
    hc = pd.read_parquet(path)
    return hc[(hc["model"] == family) & hc["split"].isin(["calibration", "test"])].copy(), family


def summarize_replay(f: pd.DataFrame, seasons: dict) -> dict:
    a = f[f["alert"]].copy()
    a["month"] = pd.to_datetime(a["check_date"]).dt.month
    lookup = {m: s for s, ms in seasons.items() for m in ms}
    a["season"] = a["month"].map(lookup)
    n_checks = f["check_date"].nunique()
    out = {}
    for (kind, det), g in a.groupby(["kind", "detector"]):
        evaluated = f[(f["kind"] == kind) & (f["detector"] == det) & f["statistic"].notna()]["check_date"].nunique()
        out[f"{kind}|{det}"] = {
            "checks_evaluated": int(evaluated),
            "checks_with_alert": int(g["check_date"].nunique()),
            "alert_rate": float(g["check_date"].nunique() / evaluated) if evaluated else float("nan"),
            "alerts_by_season": g.groupby("season")["check_date"].nunique().to_dict(),
            "alerts_by_year": g.groupby(pd.to_datetime(g["check_date"]).dt.year)["check_date"].nunique().astype(int).to_dict(),
            "targets": g["target"].value_counts().to_dict(),
        }
    return {"n_checks": int(n_checks), "by_detector": out}


def perturb(daily: pd.DataFrame, kind: str, spec: dict, onset: pd.Timestamp) -> pd.DataFrame:
    d = daily.copy()
    end = onset + pd.Timedelta(days=spec["days"] - 1)
    if kind == "temperature_bias":
        for c in ("temperature_2m", "temperature_2m_min", "temperature_2m_max"):
            d.loc[onset:end, c] += spec["offset"]
    elif kind == "snow_sensor_dropout":
        d.loc[onset:end, "snow_frac_valid"] = spec["value"]
    elif kind == "discharge_rating_shift":
        d.loc[onset:, "discharge_m3s"] *= spec["scale"]
    return d


def synthetic_evaluation(daily, table, preds, cfg, fcfg) -> dict:
    sc = cfg["synthetic_eval"]
    rng = np.random.default_rng(sc["seed"])
    lags, horizons, warm = fcfg["availability_lag_days"], fcfg["horizons"], fcfg["warmup_days"]
    step = pd.Timedelta(days=cfg["check_every_days"])
    results = {}
    for kind, spec in sc["events"].items():
        lo = pd.Timestamp(sc["onset_range"][0])
        if kind == "discharge_rating_shift" and preds is not None:
            lo = max(lo, pd.Timestamp("2022-03-01"))  # residual reference needs out-of-sample history
        hi = pd.Timestamp(sc["onset_range"][1])
        onsets = [lo + pd.Timedelta(days=int(x)) for x in rng.integers(0, (hi - lo).days, sc["n_events_per_type"])]
        rows = []
        for onset in onsets:
            dates = list(pd.date_range(onset - 4 * step, onset + pd.Timedelta(days=sc["max_delay_days"]), freq=step))
            pert_daily = perturb(daily, kind, spec, onset)
            pert_table = build_features(pert_daily, lags, horizons).iloc[warm:]
            pp = None
            if preds is not None:
                pp = preds.copy()
                if kind == "discharge_rating_shift":
                    pp.loc[pp["target_date"] >= onset, "obs"] *= spec["scale"]
            clean = run_checks(table, daily, preds, dates, cfg, lags)
            pert = run_checks(pert_table, pert_daily, pp, dates, cfg, lags)
            for det in ("baseline", "season_aware"):
                rel = {"rule"} | {det}
                c = clean[clean["detector"].isin(rel) & clean["alert"]]
                p = pert[pert["detector"].isin(rel) & pert["alert"]]
                p_after = p[pd.to_datetime(p["check_date"]) >= onset]
                c_after = c[pd.to_datetime(c["check_date"]) >= onset]
                first = pd.to_datetime(p_after["check_date"]).min() if not p_after.empty else None
                rows.append(
                    {
                        "onset": str(onset.date()),
                        "detector": det,
                        "detected": first is not None,
                        "delay_days": (first - onset).days if first is not None else None,
                        "clean_alert_in_window": not c_after.empty,
                        "alert_kinds": sorted(set(p_after["kind"])),
                    }
                )
        df = pd.DataFrame(rows)
        summary = {}
        for det, g in df.groupby("detector"):
            tp = int(g["detected"].sum())
            # Alerts that also occur without any perturbation cannot be credited to the event.
            credited = int((g["detected"] & ~g["clean_alert_in_window"]).sum())
            fp = int(g["clean_alert_in_window"].sum())
            summary[det] = {
                "events": len(g),
                "detected": tp,
                "detected_without_clean_alarm": credited,
                "missed": int(len(g) - tp),
                "recall": tp / len(g),
                "clean_windows_with_alarm": fp,
                "false_alarm_window_rate": fp / len(g),
                "precision_event_level": credited / (credited + fp) if (credited + fp) else float("nan"),
                "median_delay_days": float(g["delay_days"].dropna().median()) if tp else None,
                "delay_days": g["delay_days"].dropna().astype(int).tolist(),
            }
        results[kind] = {"spec": spec, "summary": summary, "events": rows}
    return results


def markdown(rep: dict) -> str:
    L = [f"# Drift replay ({rep['mode']} mode)", "", rep["note"], "", "## Historical replay (real inputs)", "",
         f"Weekly checks: {rep['replay']['n_checks']}, {rep['replay']['first_check']} .. {rep['replay']['last_check']}.", "",
         "| kind | detector | checks evaluated | checks with alert | alert rate | alerts by season |", "|---|---|---|---|---|---|"]
    for k, v in sorted(rep["replay"]["by_detector"].items()):
        kind, det = k.split("|")
        L.append(f"| {kind} | {det} | {v['checks_evaluated']} | {v['checks_with_alert']} | {v['alert_rate']:.3f} | {v['alerts_by_season']} |")
    L += ["", "## Controlled SYNTHETIC perturbations (not real events)", "",
          "| event | detector | recall | median delay (d) | missed | clean windows with alarm | event precision |", "|---|---|---|---|---|---|---|"]
    for kind, r in rep["synthetic"].items():
        for det, s in r["summary"].items():
            md = "-" if s["median_delay_days"] is None else f"{s['median_delay_days']:.0f}"
            L.append(f"| {kind} | {det} | {s['recall']:.2f} ({s['detected']}/{s['events']}) | {md} | {s['missed']} | {s['clean_windows_with_alarm']}/{s['events']} | {s['precision_event_level']:.2f} |")
    L += ["", "## Documented real events (context only)", ""]
    for e in rep["documented_events"]:
        L.append(f"- {e['label']} ({e['start']}..{e['end']}): alerts within 30 days after start: {e['alerts_within_30d']}")
    return "\n".join(L) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=config.mode(), choices=config.MODES)
    parser.add_argument("--latest", action="store_true", help="single operational check at the newest data")
    parser.add_argument("--skip-synthetic", action="store_true")
    args = parser.parse_args()
    cfg = config.load_yaml("drift")
    fcfg = config.load_yaml("forecast")
    gov = config.load_yaml("governance")
    table, meta = load_latest(args.mode)
    frames = load_raw(args.mode)
    daily = merge_daily(frames, str(table.index.min().date()), str(table.index.max().date()))
    preds, family = out_of_sample(args.mode)
    lags = fcfg["availability_lag_days"]

    if args.latest:
        T = table.index.max()
        f = run_checks(table, daily, preds, list(pd.date_range(T - pd.Timedelta(days=7 * 3), T, freq="7D")), cfg, lags)
        now = f[(f["check_date"] == str(T.date())) & f["alert"] & (f["detector"] != "baseline")]
        staleness = (pd.Timestamp(datetime.now(UTC).date()) - T).days
        rec = recommend(now, gov["retraining"], cfg["residual"]["qs_ratio_alert"])
        out = {"check_date": str(T.date()), "staleness_days": staleness, "stale": staleness > cfg["data_quality"]["max_staleness_days"],
               "severity": severity(now), "alerts": now.to_dict("records"), "recommendation": rec,
               "generated_utc": datetime.now(UTC).isoformat(timespec="seconds")}
        # Persist the operational check (the scheduled job's container is discarded after it runs).
        reports = config.reports_dir(args.mode)
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "drift_latest.json").write_text(json.dumps(out, indent=2, default=str))
        print(json.dumps(out, indent=2, default=str))
        return

    start = max(table.index.min() + pd.Timedelta(days=60), pd.Timestamp("2016-01-01"))
    dates = list(pd.date_range(start, table.index.max(), freq=f"{cfg['check_every_days']}D"))
    findings = run_checks(table, daily, preds, dates, cfg, lags)
    art = config.artifact_dir(args.mode)
    art.mkdir(parents=True, exist_ok=True)
    findings.drop(columns=["detail"]).assign(detail=findings["detail"].map(json.dumps)).to_parquet(art / "drift_findings.parquet", index=False)

    # Per-check severity and tier recommendation (season-aware + rule detectors).
    decisions = []
    for d, g in findings[findings["alert"] & (findings["detector"] != "baseline")].groupby("check_date"):
        rec = recommend(g, gov["retraining"], cfg["residual"]["qs_ratio_alert"])
        decisions.append({"check_date": d, "severity": severity(g), "tier": rec["tier"], "action": rec["action"], "reasons": "; ".join(map(str, rec["reasons"]))})

    rep = {
        "mode": args.mode,
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset_id": meta["dataset_id"],
        "forecast_model_family": family,
        "note": "Real-data replay has no ground-truth drift labels; alert rates there describe behaviour, not accuracy. "
        "Accuracy is measured only on controlled synthetic perturbations.",
        "replay": {**summarize_replay(findings, fcfg["seasons"]), "first_check": str(dates[0].date()), "last_check": str(dates[-1].date())},
        "documented_events": [],
        "decisions": decisions,
    }
    alerts = findings[findings["alert"]]
    for e in cfg.get("documented_events", []):
        s = pd.Timestamp(e["start"])
        near = alerts[(pd.to_datetime(alerts["check_date"]) >= s) & (pd.to_datetime(alerts["check_date"]) <= s + pd.Timedelta(days=30))]
        rep["documented_events"].append({**e, "alerts_within_30d": sorted({f"{r.kind}/{r.detector}/{r.target}" for r in near.itertuples()})})
    rep["synthetic"] = {} if args.skip_synthetic else synthetic_evaluation(daily, table, preds, cfg, fcfg)

    reports = config.reports_dir(args.mode)
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "drift_replay.json").write_text(json.dumps(rep, indent=2, default=str))
    (reports / "drift_replay.md").write_text(markdown(rep), encoding="utf-8")
    (reports / "retraining_history.json").write_text(json.dumps({"source": "drift replay recommendations (no retraining executed)", "decisions": decisions}, indent=2))
    print(markdown(rep))


if __name__ == "__main__":
    main()
