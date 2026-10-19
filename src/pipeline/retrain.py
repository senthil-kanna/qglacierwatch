"""Tier 2 (recalibrate) and Tier 3 (retrain) of the retraining policy. Never promotes.

Both tiers score the candidate and the incumbent on the same most-recent labelled window, which
neither has been fitted or calibrated on, then register the candidate and run the gate. Promotion
stays a separate, manual step (python -m src.registry.registry promote ...).

The model configuration is reused from the incumbent; no new tuning happens here, so the evaluation
window is not used for selection.

Usage:
    python -m src.pipeline.retrain --tier 3 --eval-start 2025-01-01 --eval-end 2025-12-31 --reason "residual drift"
"""

import argparse
import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from src import config
from src.evaluate.metrics import score_all
from src.evaluate.splits import Period, issue_mask
from src.features.build import load_latest
from src.models.calibration import CQR
from src.pipeline.train import git_sha, make_factories
from src.registry.registry import registry_for


def _idx(table, period, h, embargo=True):
    m = issue_mask(table.index, period, h, embargo).to_numpy()
    sub = table.index[m]
    return sub[table.loc[sub, f"y_h{h}"].notna().to_numpy()]


def _predict(members, cqr, table, idx):
    q = np.sort(np.mean([m.predict(table, idx) for m in members], axis=0), axis=1)
    return cqr.apply(q)


def score_bundle(bundle, table, window: Period, clim) -> dict:
    by_h = {}
    for h in bundle["horizons"]:
        idx = _idx(table, window, h, embargo=False)
        y = table.loc[idx, f"y_h{h}"]
        s = score_all(y, _predict(bundle["models"][h], bundle["cqr"][h], table, idx))
        by_h[f"h{h}"] = {**s, "qs_climatology": score_all(y, clim[h].predict(table, idx))["qs"]}
    return {"window": [str(window.start.date()), str(window.end.date())], "by_horizon": by_h, "mean_qs": float(np.mean([v["qs"] for v in by_h.values()]))}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default=config.mode(), choices=config.MODES)
    p.add_argument("--tier", type=int, choices=[2, 3], required=True)
    p.add_argument("--eval-start", required=True)
    p.add_argument("--eval-end", required=True)
    p.add_argument("--cal-days", type=int, default=365)
    p.add_argument("--reason", default="")
    args = p.parse_args()

    cfg = config.load_yaml("forecast")
    table, dmeta = load_latest(args.mode)
    reg = registry_for(args.mode)
    state = reg.list()
    inc_id = state["production"] or (sorted(state["models"].items(), key=lambda kv: kv[1]["registered_utc"])[-1][0] if state["models"] else None)
    if inc_id is None:
        raise SystemExit("No incumbent model registered; run the training pipeline first.")
    inc_card, inc = reg.card(inc_id), reg.load_bundle(inc_id)

    window = Period(pd.Timestamp(args.eval_start), pd.Timestamp(args.eval_end))
    cal_end = window.start - pd.Timedelta(days=1)
    cal = Period(cal_end - pd.Timedelta(days=args.cal_days - 1), cal_end)
    train = Period(pd.Timestamp(cfg["splits"]["train"][0]), cal.start - pd.Timedelta(days=1))

    factories = make_factories(cfg, quick=False)
    clim = {h: dict(factories["climatology"])["window15"](0).fit(table, h, _idx(table, train, h)) for h in inc["horizons"]}

    if args.tier == 2:
        models = inc["models"]
        family = f"{inc['family']}+recal"
        train_period = inc_card["train_period"]
    else:
        factory = dict(factories[inc["family"]])[inc_card["config"]]
        models = {h: [factory(s).fit(table, h, _idx(table, train, h)) for s in inc_card["seeds"]] for h in inc["horizons"]}
        family = inc["family"]
        train_period = [str(train.start.date()), str(train.end.date())]
    cqr = {}
    for h in inc["horizons"]:
        idx = _idx(table, cal, h)
        q = np.sort(np.mean([m.predict(table, idx) for m in models[h]], axis=0), axis=1)
        cqr[h] = CQR(cfg["calibration"]["target_coverage"]).fit(table.loc[idx, f"y_h{h}"], q)

    bundle = {**inc, "family": family, "models": models, "cqr": cqr}
    cand_eval = score_bundle(bundle, table, window, clim)
    inc_eval = {**score_bundle(inc, table, window, clim), "model_id": inc_id}
    card = {
        "model_family": family,
        "dataset_id": dmeta["dataset_id"],
        "git_sha": git_sha(),
        "config": inc_card["config"],
        "seeds": inc_card["seeds"],
        "train_period": train_period,
        "calibration_period": [str(cal.start.date()), str(cal.end.date())],
        "target_source": dmeta["target_source"],
        "availability_lag_days": dmeta["availability_lag_days"],
        "parent_model_id": inc_id,
        "retraining_tier": args.tier,
        "retraining_reason": args.reason,
        "eval": cand_eval,
        "incumbent_eval": inc_eval,
    }
    model_id = reg.register(bundle, card)
    decision = reg.gate(model_id, config.load_yaml("governance")["gate"])

    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "tier": args.tier,
        "reason": args.reason,
        "incumbent": inc_id,
        "incumbent_is_production": state["production"] == inc_id,
        "candidate": model_id,
        "eval_window": cand_eval["window"],
        "candidate_mean_qs": cand_eval["mean_qs"],
        "incumbent_mean_qs": inc_eval["mean_qs"],
        "gate_passed": decision["passed"],
        "gate_reasons": decision["reasons"],
        "promoted": False,
    }
    path = config.reports_dir(args.mode) / "retraining_runs.json"
    runs = json.loads(path.read_text()) if path.exists() else []
    runs.append(entry)
    path.write_text(json.dumps(runs, indent=2))
    print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
