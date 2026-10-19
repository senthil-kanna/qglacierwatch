"""File-backed model registry with lineage, a promotion gate, manual approval and rollback.

Layout under artifacts/<mode>/registry/:
    registry.json          models, current production id, production history
    audit.jsonl            append-only log of every register/evaluate/promote/rollback event
    models/<model_id>/     bundle.joblib + card.json (lineage, metrics, config)

Usage:
    python -m src.registry.registry list
    python -m src.registry.registry gate --model-id ID
    python -m src.registry.registry promote --model-id ID --approver "Name" --reason "..."
    python -m src.registry.registry rollback --approver "Name" --reason "..."
"""

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import joblib

from src import config


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Registry:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = self.root / "registry.json"
        self.audit = self.root / "audit.jsonl"
        if not self.index.exists():
            self._save({"models": {}, "production": None, "production_history": []})

    def _load(self) -> dict:
        return json.loads(self.index.read_text())

    def _save(self, state: dict) -> None:
        tmp = self.index.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(self.index)

    def _log(self, event: str, **fields) -> None:
        with open(self.audit, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": _now(), "event": event, **fields}) + "\n")

    # -- registration -------------------------------------------------------------------------
    def register(self, bundle: dict, card: dict) -> str:
        model_id = f"{card['model_family']}-{card['dataset_id']}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"
        d = self.root / "models" / model_id
        d.mkdir(parents=True)
        joblib.dump(bundle, d / "bundle.joblib")
        card = {**card, "model_id": model_id, "registered_utc": _now(), "stage": "candidate"}
        (d / "card.json").write_text(json.dumps(card, indent=2, default=str))
        state = self._load()
        state["models"][model_id] = {k: card[k] for k in ("model_family", "dataset_id", "registered_utc", "stage")}
        self._save(state)
        self._log("register", model_id=model_id, dataset_id=card["dataset_id"], family=card["model_family"])
        return model_id

    def card(self, model_id: str) -> dict:
        return json.loads((self.root / "models" / model_id / "card.json").read_text())

    def load_bundle(self, model_id: str) -> dict:
        return joblib.load(self.root / "models" / model_id / "bundle.joblib")

    @property
    def production(self) -> str | None:
        return self._load()["production"]

    def list(self) -> dict:
        return self._load()

    # -- governance ---------------------------------------------------------------------------
    def gate(self, model_id: str, rules: dict) -> dict:
        """Check a candidate against absolute floors and the incumbent on the same window."""
        card = self.card(model_id)
        cand = card["eval"]
        reasons, passed = [], True
        inc_id = self.production
        inc = self.card(inc_id)["eval"] if inc_id else None
        # A retraining run re-scores the incumbent on the candidate's window; prefer that.
        rescore = card.get("incumbent_eval")
        if inc_id and rescore and rescore.get("model_id") == inc_id:
            inc = rescore

        if inc and inc["window"] != cand["window"]:
            passed = False
            reasons.append(f"evaluation windows differ ({cand['window']} vs incumbent {inc['window']}); re-evaluate on a common window")
        for h, m in cand["by_horizon"].items():
            if m["n"] < rules["min_eval_samples"]:
                passed = False
                reasons.append(f"{h}: only {m['n']} evaluation samples (< {rules['min_eval_samples']})")
            floor = rules["min_nse"].get(h)
            if floor is not None and not (m["nse"] >= floor):
                passed = False
                reasons.append(f"{h}: NSE {m['nse']:.3f} below floor {floor}")
            lo, hi = rules["coverage_band"]
            if not (lo <= m["coverage_80"] <= hi):
                passed = False
                reasons.append(f"{h}: P10-P90 coverage {m['coverage_80']:.3f} outside [{lo}, {hi}]")
            if rules.get("must_beat_climatology") and not (m["qs"] < m["qs_climatology"]):
                passed = False
                reasons.append(f"{h}: QS {m['qs']:.2f} does not beat climatology {m['qs_climatology']:.2f}")
        if inc and inc["window"] == cand["window"]:
            ratio = cand["mean_qs"] / inc["mean_qs"]
            if ratio > rules["max_qs_ratio_vs_incumbent"]:
                passed = False
                reasons.append(f"mean QS ratio vs incumbent {inc_id} is {ratio:.3f} > {rules['max_qs_ratio_vs_incumbent']}")
            else:
                reasons.append(f"mean QS ratio vs incumbent {ratio:.3f} (pass)")
        elif not inc:
            reasons.append("no incumbent: first production model, absolute floors only")
        decision = {"model_id": model_id, "incumbent": inc_id, "passed": passed, "reasons": reasons, "ts": _now()}
        self._log("gate", **decision)
        return decision

    def promote(self, model_id: str, approver: str, reason: str, rules: dict) -> dict:
        if not approver or not approver.strip():
            raise PermissionError("Promotion requires a named approver.")
        decision = self.gate(model_id, rules)
        if not decision["passed"]:
            self._log("promote_rejected", model_id=model_id, approver=approver, reasons=decision["reasons"])
            raise PermissionError(f"Gate failed, not promoting: {decision['reasons']}")
        state = self._load()
        prev = state["production"]
        if prev:
            state["models"][prev]["stage"] = "archived"
        state["models"][model_id]["stage"] = "production"
        state["production"] = model_id
        state["production_history"].append({"model_id": model_id, "previous": prev, "approver": approver, "reason": reason, "ts": _now()})
        self._save(state)
        self._log("promote", model_id=model_id, previous=prev, approver=approver, reason=reason)
        return decision

    def rollback(self, approver: str, reason: str) -> str:
        if not approver or not approver.strip():
            raise PermissionError("Rollback requires a named approver.")
        state = self._load()
        hist = state["production_history"]
        if not hist or not hist[-1]["previous"]:
            raise RuntimeError("No previous production model to roll back to.")
        current, target = hist[-1]["model_id"], hist[-1]["previous"]
        state["models"][current]["stage"] = "rolled_back"
        state["models"][target]["stage"] = "production"
        state["production"] = target
        hist.append({"model_id": target, "previous": current, "approver": approver, "reason": f"ROLLBACK: {reason}", "ts": _now()})
        self._save(state)
        self._log("rollback", model_id=target, previous=current, approver=approver, reason=reason)
        return target

    def remove_all(self) -> None:
        shutil.rmtree(self.root)


def registry_for(m: str) -> Registry:
    return Registry(config.artifact_dir(m) / "registry")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["list", "gate", "promote", "rollback"])
    parser.add_argument("--mode", default=config.mode(), choices=config.MODES)
    parser.add_argument("--model-id")
    parser.add_argument("--approver", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    reg = registry_for(args.mode)
    rules = config.load_yaml("governance")["gate"]
    if args.command == "list":
        print(json.dumps(reg.list(), indent=2))
    elif args.command == "gate":
        print(json.dumps(reg.gate(args.model_id, rules), indent=2))
    elif args.command == "promote":
        print(json.dumps(reg.promote(args.model_id, args.approver, args.reason, rules), indent=2))
    else:
        print(f"Production is now {reg.rollback(args.approver, args.reason)}")


if __name__ == "__main__":
    main()
