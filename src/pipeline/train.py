"""Model selection, final training, calibration and (optionally) held-out test evaluation.

Stages
  1. Rolling-origin CV on the development years (configs/forecast.yaml: cv_validation_years) for
     every model and every grid config. Selection uses mean CV QS only.
  2. Refit the selected configs on the train period for each seed; the forecast is the mean of
     seed quantiles. Fit CQR on the calibration period.
  3. With --final: score the untouched test period once, run paired block-bootstrap comparisons,
     write the hindcast store, and register the selected model as a candidate.

Usage:
    python -m src.pipeline.train --mode demo --quick          # minutes; for smoke tests
    python -m src.pipeline.train --mode real                  # CV + calibration only
    python -m src.pipeline.train --mode real --final          # also touches the test set
"""

import argparse
import json
import platform
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from src import config
from src.evaluate.bootstrap import block_bootstrap_diff
from src.evaluate.metrics import quantile_score, score_all, score_by_season
from src.evaluate.splits import assert_ordered, cv_folds, issue_mask, main_splits
from src.features.build import load_latest
from src.ingest.provenance import sha256
from src.models.baselines import Climatology, Persistence
from src.models.calibration import make_cqr
from src.models.gbm import GBMQuantile
from src.models.lstm import QuantileLSTM
from src.registry.registry import registry_for


def git_sha() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", "configs"], capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def make_factories(cfg: dict, quick: bool) -> dict:
    """name -> list of (config_label, factory(seed)) candidates. Baselines have one config."""
    lc = cfg["lstm"]
    gbm_grid = cfg["gbm"]["grid"][:2] if quick else cfg["gbm"]["grid"]
    lstm_grid = [{**g, "epochs": 5} for g in lc["grid"][:1]] if quick else lc["grid"]

    def gbm(g):
        return lambda seed: GBMQuantile({**g, **cfg["gbm"]["common"]}, seed)

    def lstm(g):
        return lambda seed: QuantileLSTM(g, lc["seq_len"], lc["batch_size"], lc["patience"], seed)

    return {
        "persistence": [("default", lambda seed: Persistence())],
        "climatology": [("window15", lambda seed: Climatology(15))],
        "gbm_quantile": [(json.dumps(g, sort_keys=True), gbm(g)) for g in gbm_grid],
        "quantile_lstm": [(json.dumps(g, sort_keys=True), lstm(g)) for g in lstm_grid],
    }


def _idx(table, period, h, embargo=True):
    m = issue_mask(table.index, period, h, embargo)
    sub = table.index[m.to_numpy()]
    return sub[table.loc[sub, f"y_h{h}"].notna().to_numpy()]


def run_cv(table, cfg, factories, log) -> pd.DataFrame:
    rows = []
    for name, cands in factories.items():
        for label, factory in cands:
            for tr, va in cv_folds(cfg):
                for h in cfg["horizons"]:
                    tri, vai = _idx(table, tr, h), _idx(table, va, h, embargo=False)
                    t0 = time.perf_counter()
                    model = factory(cfg["seeds"][0]).fit(table, h, tri)
                    qp = model.predict(table, vai)
                    s = score_all(table.loc[vai, f"y_h{h}"], qp)
                    rows.append({"model": name, "config": label, "fold": va.start.year, "h": h, **s, "seconds": time.perf_counter() - t0})
            mean_qs = np.mean([r["qs"] for r in rows if r["model"] == name and r["config"] == label])
            log(f"  CV {name:14s} {label[:70]:70s} mean QS {mean_qs:7.3f}")
    return pd.DataFrame(rows)


def select(cv: pd.DataFrame) -> dict:
    agg = cv.groupby(["model", "config"])["qs"].mean().reset_index()
    return {m: g.sort_values("qs").iloc[0]["config"] for m, g in agg.groupby("model")}


def fit_final(table, cfg, factories, chosen, splits, log) -> dict:
    """Fit each model on the train period for each seed; returns fitted objects per (model, h)."""
    fitted = {}
    for name, cands in factories.items():
        factory = dict(cands)[chosen[name]]
        seeds = cfg["seeds"] if name in ("gbm_quantile", "quantile_lstm") else [0]
        for h in cfg["horizons"]:
            tri = _idx(table, splits["train"], h)
            members, secs = [], []
            for seed in seeds:
                t0 = time.perf_counter()
                members.append(factory(seed).fit(table, h, tri))
                secs.append(time.perf_counter() - t0)
            fitted[(name, h)] = {"members": members, "train_seconds": secs, "n_train": len(tri)}
        log(f"  fitted {name} ({len(seeds)} seed(s)) on {splits['train'].start.date()}..{splits['train'].end.date()}")
    return fitted


def ensemble_predict(entry, table, idx) -> tuple[np.ndarray, list[np.ndarray]]:
    per_seed = [m.predict(table, idx) for m in entry["members"]]
    return np.sort(np.mean(per_seed, axis=0), axis=1), per_seed


def calibrate(table, cfg, fitted, splits) -> dict:
    cal = {}
    for (name, h), entry in fitted.items():
        idx = _idx(table, splits["calibration"], h)
        qp, _ = ensemble_predict(entry, table, idx)
        cal[(name, h)] = make_cqr(cfg).fit(table.loc[idx, f"y_h{h}"], qp, idx + pd.Timedelta(days=h))
    return cal


def evaluate_period(table, cfg, fitted, cal, period, label) -> tuple[dict, pd.DataFrame]:
    results, frames = {}, []
    for (name, h), entry in fitted.items():
        idx = _idx(table, period, h, embargo=False)
        raw, per_seed = ensemble_predict(entry, table, idx)
        tdates = idx + pd.Timedelta(days=h)
        calq = cal[(name, h)].apply(raw, tdates)
        y = table.loc[idx, f"y_h{h}"].to_numpy()
        t0 = time.perf_counter()
        entry["members"][0].predict(table, idx)
        infer = time.perf_counter() - t0
        results[f"{name}|h{h}"] = {
            "model": name,
            "h": h,
            "raw": score_all(y, raw),
            "calibrated": score_all(y, calq),
            "seasonal_calibrated": score_by_season(tdates, y, calq, cfg["seasons"]),
            "per_seed_raw_qs": [float(np.mean(quantile_score(y, q))) for q in per_seed],
            "cqr_q_hat": cal[(name, h)].q_hat,
            "cqr_q_hat_by_season": cal[(name, h)].q_hat_by_season,
            "cqr_n": cal[(name, h)].n,
            "train_seconds": entry["train_seconds"],
            "inference_seconds_per_member": infer,
            "n_params": entry["members"][0].n_params() if hasattr(entry["members"][0], "n_params") else None,
        }
        frames.append(
            pd.DataFrame(
                {
                    "issue_date": idx,
                    "target_date": tdates,
                    "h": h,
                    "model": name,
                    "split": label,
                    "obs": y,
                    "p10": calq[:, 0],
                    "p50": calq[:, 1],
                    "p90": calq[:, 2],
                    "p10_raw": raw[:, 0],
                    "p90_raw": raw[:, 2],
                }
            )
        )
    return results, pd.concat(frames, ignore_index=True)


def comparisons(preds: pd.DataFrame, cfg: dict, best: str) -> list[dict]:
    """Paired block bootstrap of per-sample QS differences on identical test issue dates."""
    out = []
    bc = cfg["bootstrap"]
    models = sorted(preds["model"].unique())
    for h in cfg["horizons"]:
        p = preds[preds["h"] == h]
        wide = {m: g.set_index("issue_date").sort_index() for m, g in p.groupby("model")}
        pairs = [(m, ref) for ref in ("climatology", "persistence") for m in models if m != ref]
        pairs += [(best, m) for m in models if m not in (best, "climatology", "persistence")]
        for a, b in pairs:
            ga, gb = wide[a], wide[b]
            common = ga.index.intersection(gb.index)
            la = quantile_score(ga.loc[common, "obs"], ga.loc[common, ["p10", "p50", "p90"]].to_numpy())
            lb = quantile_score(gb.loc[common, "obs"], gb.loc[common, ["p10", "p50", "p90"]].to_numpy())
            r = block_bootstrap_diff(la, lb, bc["block_days"], bc["n_resamples"], bc["ci"], seed=h)
            out.append({"h": h, "a": a, "b": b, "metric": "QS (calibrated)", **r})
    return out


def results_markdown(test: dict, cv_sel: pd.DataFrame, comps: list[dict], meta: dict, horizons) -> str:
    lines = [
        f"# Forecast results ({meta['mode']} mode)",
        "",
        f"Target: `{meta['target_source']}` ({'observed gauge' if meta['target_is_observed'] else 'MODELLED reanalysis, not observed discharge'}).",
        f"Dataset `{meta['dataset_id']}`, generated {meta['generated_utc']}, code `{meta['git_sha']}`.",
        "",
        "## Held-out test period (calibrated intervals)",
        "",
        "| model | h | n | NSE | KGE | MAE | RMSE | QS | cov80 | width80 | raw cov80 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for h in horizons:
        for r in test.values():
            if r["h"] != h:
                continue
            c, raw = r["calibrated"], r["raw"]
            lines.append(
                f"| {r['model']} | {h} | {c['n']} | {c['nse']:.3f} | {c['kge']:.3f} | {c['mae']:.2f} | {c['rmse']:.2f} | "
                f"{c['qs']:.2f} | {c['coverage_80']:.3f} | {c['width_80']:.1f} | {raw['coverage_80']:.3f} |"
            )
    lines += ["", "## Seasonal QS on test (calibrated)", "", "| model | h | " + " | ".join(next(iter(test.values()))["seasonal_calibrated"]) + " |"]
    lines.append("|---|---|" + "---|" * len(next(iter(test.values()))["seasonal_calibrated"]))
    for r in test.values():
        s = r["seasonal_calibrated"]
        lines.append(f"| {r['model']} | {r['h']} | " + " | ".join(f"{v['qs']:.2f} (n={v['n']}, cov {v['coverage_80']:.2f})" for v in s.values()) + " |")
    lines += ["", "## Paired block-bootstrap QS differences on test (A - B; negative = A better)", "",
              "| h | A | B | mean diff | 95% CI | P(A better) | n |", "|---|---|---|---|---|---|---|"]
    for c in comps:
        lines.append(f"| {c['h']} | {c['a']} | {c['b']} | {c['mean_diff']:.3f} | [{c['lo']:.3f}, {c['hi']:.3f}] | {c['p_a_better']:.3f} | {c['n']} |")
    lines += ["", "## CV model selection (mean QS over folds and horizons; lower is better)", "",
              "| model | config | mean CV QS |", "|---|---|---|"]
    for _, r in cv_sel.iterrows():
        lines.append(f"| {r['model']} | `{r['config']}` | {r['qs']:.3f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=config.mode(), choices=config.MODES)
    parser.add_argument("--final", action="store_true", help="evaluate on the held-out test period (do once)")
    parser.add_argument("--quick", action="store_true", help="reduced grid/epochs for smoke tests")
    args = parser.parse_args()

    cfg = config.load_yaml("forecast")
    if args.quick:
        cfg["seeds"] = cfg["seeds"][:1]
        cfg["cv_validation_years"] = cfg["cv_validation_years"][-1:]
    table, dmeta = load_latest(args.mode)
    splits = main_splits(cfg)
    assert_ordered(splits["train"], splits["calibration"], splits["test"])
    out = config.artifact_dir(args.mode)
    reports = config.reports_dir(args.mode)
    out.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    log_path = out / "train_log.txt"

    def log(msg: str) -> None:
        print(msg, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    started = datetime.now(UTC).isoformat(timespec="seconds")
    log(f"=== train {started} mode={args.mode} final={args.final} quick={args.quick} dataset={dmeta['dataset_id']}")
    factories = make_factories(cfg, args.quick)
    cv = run_cv(table, cfg, factories, log)
    cv.to_csv(reports / "cv_scores.csv", index=False)
    chosen = select(cv)
    log(f"  selected: {json.dumps(chosen)}")

    fitted = fit_final(table, cfg, factories, chosen, splits, log)
    cal = calibrate(table, cfg, fitted, splits)
    cal_scores, cal_preds = evaluate_period(table, cfg, fitted, cal, splits["calibration"], "calibration")
    learned = ["gbm_quantile", "quantile_lstm"]
    cv_mean = cv.groupby(["model", "config"])["qs"].mean().reset_index()
    sel_scores = {m: float(cv_mean[(cv_mean.model == m) & (cv_mean.config == chosen[m])]["qs"].iloc[0]) for m in chosen}
    best = min(learned, key=lambda m: sel_scores[m])
    log(f"  best learned model by CV QS: {best} ({sel_scores[best]:.3f})")

    meta = {
        "mode": args.mode,
        "dataset_id": dmeta["dataset_id"],
        "target_source": dmeta["target_source"],
        "target_is_observed": dmeta["target_is_observed"],
        "generated_utc": started,
        "git_sha": git_sha(),
        "protocol_sha256": {
            p: sha256(config.ROOT / p) for p in ("docs/protocol.md", "configs/forecast.yaml", "configs/governance.yaml")
        }
        | ({str(o.relative_to(config.ROOT)): sha256(o)} if (o := config.overlay_file("forecast")) else {}),
        "splits": cfg["splits"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "selected_configs": chosen,
        "cv_mean_qs": sel_scores,
        "best_learned_model": best,
        "seeds": cfg["seeds"],
        "quick": args.quick,
        "test_evaluated": args.final,
    }
    summary: dict[str, Any] = {"meta": meta, "calibration_period": cal_scores}
    preds = [cal_preds]

    # In-sample fits on the train period, stored only so the dashboard can replay them as such.
    tr_scores, tr_preds = evaluate_period(table, cfg, fitted, cal, splits["train"], "train_in_sample")
    preds.append(tr_preds)

    if args.final:
        with open(out / "test_access.log", "a", encoding="utf-8") as fh:
            fh.write(f"{started} test period evaluated (dataset {dmeta['dataset_id']}, code {meta['git_sha']})\n")
        test_scores, test_preds = evaluate_period(table, cfg, fitted, cal, splits["test"], "test")
        comps = comparisons(test_preds, cfg, best)
        summary["test_period"] = test_scores
        summary["comparisons"] = comps
        preds.append(test_preds)
        cv_sel = cv_mean.sort_values(["model", "qs"])
        (reports / "forecast_results.md").write_text(results_markdown(test_scores, cv_sel, comps, meta, cfg["horizons"]), encoding="utf-8")

        reg = registry_for(args.mode)
        by_h = {}
        for h in cfg["horizons"]:
            r = test_scores[f"{best}|h{h}"]["calibrated"]
            by_h[f"h{h}"] = {**r, "qs_climatology": test_scores[f"climatology|h{h}"]["calibrated"]["qs"]}
        bundle = {
            "family": best,
            "horizons": cfg["horizons"],
            "models": {h: fitted[(best, h)]["members"] for h in cfg["horizons"]},
            "cqr": {h: cal[(best, h)] for h in cfg["horizons"]},
            "feature_cols": dmeta["feature_cols"],
        }
        card = {
            "model_family": best,
            "dataset_id": dmeta["dataset_id"],
            "git_sha": meta["git_sha"],
            "config": chosen[best],
            "seeds": cfg["seeds"],
            "train_period": cfg["splits"]["train"],
            "calibration_period": cfg["splits"]["calibration"],
            "target_source": dmeta["target_source"],
            "availability_lag_days": dmeta["availability_lag_days"],
            "eval": {"window": cfg["splits"]["test"], "by_horizon": by_h, "mean_qs": float(np.mean([v["qs"] for v in by_h.values()]))},
        }
        model_id = reg.register(bundle, card)
        summary["registered_model_id"] = model_id
        decision = reg.gate(model_id, config.load_yaml("governance")["gate"])
        summary["gate_decision"] = decision
        log(f"  registered candidate {model_id}; gate passed={decision['passed']}: {decision['reasons']}")

    pd.concat(preds, ignore_index=True).to_parquet(out / "hindcasts.parquet", index=False)
    (reports / "forecast_results.json").write_text(json.dumps(summary, indent=2, default=str))
    log(f"=== done; reports in {reports}")


if __name__ == "__main__":
    main()
