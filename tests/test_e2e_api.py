"""End-to-end smoke test on the SYNTHETIC fixture: generate -> features -> train (quick, final)
-> registry -> API. Runs in temporary directories, never touches data/ or artifacts/."""

import sys

import pytest
from fastapi.testclient import TestClient

from src import config
from src.data import synthetic
from src.features import build


@pytest.fixture(scope="module")
def demo_env(tmp_path_factory):
    root = tmp_path_factory.mktemp("qgw")
    mp = pytest.MonkeyPatch()
    mp.setenv("QGW_MODE", "demo")
    mp.setenv("QGW_DATA", str(root / "data"))
    mp.setenv("QGW_ARTIFACTS", str(root / "artifacts"))
    mp.setenv("QGW_REPORTS", str(root / "reports"))
    mp.delenv("QGW_API_KEY", raising=False)
    synthetic.write(config.raw_dir("demo"))
    table, meta = build.build("demo")
    build.save(table, meta)
    from src.pipeline import train

    mp.setattr(sys, "argv", ["train", "--mode", "demo", "--quick", "--final"])
    train.main()
    yield root
    mp.undo()


@pytest.fixture(scope="module")
def client(demo_env):
    from api.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.slow
def test_pipeline_outputs_exist(demo_env):
    assert (demo_env / "artifacts" / "demo" / "hindcasts.parquet").exists()
    assert (demo_env / "reports" / "demo" / "forecast_results.md").exists()
    assert (demo_env / "artifacts" / "demo" / "test_access.log").read_text().count("test period evaluated") == 1


@pytest.mark.slow
def test_health_reports_unpromoted_candidate(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "demo"
    assert body["model_status"] == "unpromoted_candidate"
    assert body["freshness"]["target_source"] == "SYNTHETIC"


@pytest.mark.slow
def test_operational_forecast_schema_and_ordering(client):
    r = client.get("/v1/forecast")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "operational"
    assert body["target_is_observed"] is False
    assert [f["horizon_days"] for f in body["forecasts"]] == [1, 7, 30]
    for f in body["forecasts"]:
        assert 0 <= f["p10"] <= f["p50"] <= f["p90"]
    assert body["model_id"] and body["dataset_id"]


@pytest.mark.slow
def test_replay_and_hindcast(client):
    r = client.get("/v1/forecast", params={"issue_date": "2024-07-15"})
    assert r.status_code == 200 and r.json()["kind"] == "replay_with_serving_model"
    assert r.json()["forecasts"][0]["observed"] is not None
    h = client.get("/v1/hindcast", params={"issue_date": "2024-07-15", "model": "climatology"})
    assert h.status_code == 200 and h.json()["kind"] == "hindcast:test"


@pytest.mark.slow
def test_api_validation_and_errors(client):
    assert client.get("/v1/forecast", params={"issue_date": "not-a-date"}).status_code == 422
    r = client.get("/v1/forecast", params={"issue_date": "1990-01-01"})
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    assert client.get("/v1/hindcast", params={"issue_date": "2024-07-15", "model": "rm -rf"}).status_code == 422
    assert client.get("/v1/reports/secrets").status_code == 404
    assert client.get("/v1/reports/forecast_results").status_code == 200


@pytest.mark.slow
def test_tier2_recalibration_registers_candidate_without_promoting(demo_env, monkeypatch):
    import json

    from src.pipeline import retrain
    from src.registry.registry import registry_for

    before = registry_for("demo").list()
    monkeypatch.setattr(sys, "argv", ["retrain", "--mode", "demo", "--tier", "2", "--eval-start", "2025-01-01", "--eval-end", "2025-12-31", "--reason", "test"])
    retrain.main()
    after = registry_for("demo").list()
    assert len(after["models"]) == len(before["models"]) + 1
    assert after["production"] == before["production"]  # never auto-promoted
    runs = json.loads((demo_env / "reports" / "demo" / "retraining_runs.json").read_text())
    assert runs[-1]["tier"] == 2 and runs[-1]["promoted"] is False
    assert runs[-1]["eval_window"] == ["2025-01-01", "2025-12-31"]


@pytest.mark.slow
def test_api_key_and_rate_limit(client, monkeypatch):
    monkeypatch.setenv("QGW_API_KEY", "test-key")
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers={"X-API-Key": "test-key"}).status_code == 200
    monkeypatch.delenv("QGW_API_KEY")
    monkeypatch.setenv("QGW_RATE_PER_MIN", "3")
    client.app.state.buckets.clear()
    codes = [client.get("/v1/models").status_code for _ in range(6)]
    assert 429 in codes
