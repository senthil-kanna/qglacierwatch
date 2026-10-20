import json

import pytest

from src import config
from src.registry.registry import Registry

RULES = config.load_yaml("governance")["gate"]
WINDOW = ["2023-01-01", "2025-12-31"]


def _card(qs: float, nse: float = 0.9, cov: float = 0.8, window=WINDOW, n: int = 900) -> dict:
    by_h = {
        h: {"n": n, "nse": nse, "coverage_80": cov, "qs": qs, "qs_climatology": 50.0}
        for h in ("h1", "h7", "h30")
    }
    return {"model_family": "gbm_quantile", "dataset_id": "abc123", "eval": {"window": window, "by_horizon": by_h, "mean_qs": qs}}


def test_promotion_requires_named_approver(tmp_path):
    reg = Registry(tmp_path)
    mid = reg.register({"dummy": 1}, _card(10.0))
    with pytest.raises(PermissionError):
        reg.promote(mid, "  ", "first", RULES)
    reg.promote(mid, "Hydrologist A", "first release", RULES)
    assert reg.production == mid


def test_worse_candidate_is_never_promoted(tmp_path):
    reg = Registry(tmp_path)
    good = reg.register({}, _card(10.0))
    reg.promote(good, "A", "first", RULES)
    worse = reg.register({}, _card(12.0))
    assert not reg.gate(worse, RULES)["passed"]
    with pytest.raises(PermissionError):
        reg.promote(worse, "A", "try anyway", RULES)
    assert reg.production == good


def test_marginal_improvement_below_threshold_is_rejected(tmp_path):
    reg = Registry(tmp_path)
    reg.promote(reg.register({}, _card(10.0)), "A", "first", RULES)
    assert not reg.gate(reg.register({}, _card(9.95)), RULES)["passed"]  # 0.5% better, needs 2%


@pytest.mark.parametrize(
    "card",
    [_card(10.0, cov=0.5), _card(10.0, nse=-1.0), _card(60.0), _card(10.0, n=30)],
    ids=["undercoverage", "nse_floor", "worse_than_climatology", "too_few_samples"],
)
def test_absolute_floors(tmp_path, card):
    reg = Registry(tmp_path)
    assert not reg.gate(reg.register({}, card), RULES)["passed"]


def test_different_eval_windows_block_promotion(tmp_path):
    reg = Registry(tmp_path)
    reg.promote(reg.register({}, _card(10.0)), "A", "first", RULES)
    other = reg.register({}, _card(5.0, window=["2024-01-01", "2025-12-31"]))
    assert not reg.gate(other, RULES)["passed"]


def test_rollback_and_audit_log(tmp_path):
    reg = Registry(tmp_path)
    a = reg.register({"v": 1}, _card(10.0))
    reg.promote(a, "A", "first", RULES)
    b = reg.register({"v": 2}, _card(9.0))
    reg.promote(b, "B", "better", RULES)
    assert reg.load_bundle(b) == {"v": 2}
    assert reg.rollback("Ops", "bad forecasts in production") == a
    assert reg.production == a
    state = reg.list()
    assert state["models"][b]["stage"] == "rolled_back"
    events = [json.loads(line)["event"] for line in reg.audit.read_text().splitlines()]
    assert events.count("promote") == 2 and "rollback" in events


def test_rollback_without_history_fails(tmp_path):
    reg = Registry(tmp_path)
    with pytest.raises(RuntimeError):
        reg.rollback("Ops", "nothing to roll back")
