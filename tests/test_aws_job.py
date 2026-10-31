"""Scheduled-job handler (src.aws_job) and the API's optional S3 hydration; no AWS access."""

import json
import os
import subprocess
import sys
import types

import pytest
from fastapi.testclient import TestClient

from src import aws_job, storage


@pytest.fixture
def calls(tmp_path, monkeypatch):
    rec = {"pull": [], "push": [], "cmd": None, "env": None}
    monkeypatch.setattr(aws_job, "WORK", tmp_path / "work")
    monkeypatch.setattr(storage, "pull", lambda parts, dest_root=None: rec["pull"].append(parts) or 0)
    monkeypatch.setattr(storage, "push", lambda parts, since=None: rec["push"].append(parts) or 3)
    for env in storage.ROOT_ENV.values():
        monkeypatch.setenv(env, "untouched")

    def fake_run(cmd, env=None, check=False):
        rec["cmd"], rec["env"] = cmd, env
        return subprocess.CompletedProcess(cmd, rec.get("code", 0))

    monkeypatch.setattr(aws_job.subprocess, "run", fake_run)
    return rec


def fake_ssm(monkeypatch, value):
    client = types.SimpleNamespace(get_parameter=lambda Name, WithDecryption: {"Parameter": {"Value": value}})
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda name: client))
    monkeypatch.setenv("QGW_EE_KEY_PARAM", "/qgw/ee-service-account-json")


def test_refresh_skips_ingest_while_key_is_placeholder(calls, monkeypatch, tmp_path):
    fake_ssm(monkeypatch, "not-configured")
    out = aws_job.handler({"job": "refresh"}, None)
    assert calls["cmd"][1:] == ["-m", "src.pipeline.refresh", "--skip-ingest"]
    assert "EE_SERVICE_ACCOUNT_JSON" not in calls["env"]
    assert calls["env"]["QGW_DATA"] == str(tmp_path / "work" / "data")
    assert "artifacts/real/hindcasts.parquet" in calls["pull"][0] and "artifacts/real" not in calls["pull"][0]
    assert out == {"job": "refresh", "args": ["--skip-ingest"], "exit_code": 0, "files_pushed": 3}


def test_refresh_runs_full_ingest_once_a_real_key_is_stored(calls, monkeypatch):
    fake_ssm(monkeypatch, '{"client_email": "x@y"}')
    aws_job.handler({"job": "refresh"}, None)
    assert calls["cmd"][1:] == ["-m", "src.pipeline.refresh"]
    assert calls["env"]["EE_SERVICE_ACCOUNT_JSON"].startswith("{")
    aws_job.handler({"job": "refresh", "skip_ingest": True}, None)
    assert calls["cmd"][-1] == "--skip-ingest"


def test_drift_job_and_failure_does_not_push(calls, monkeypatch):
    monkeypatch.delenv("QGW_EE_KEY_PARAM", raising=False)
    aws_job.handler({"job": "drift"}, None)
    assert calls["cmd"][2:] == ["src.drift.replay", "--mode", "real", "--latest"] and calls["push"] == [["reports/real"]]
    calls["code"], calls["push"] = 2, []
    with pytest.raises(RuntimeError, match="exited with 2"):
        aws_job.handler({"job": "drift"}, None)
    assert calls["push"] == []
    with pytest.raises(ValueError):
        aws_job.handler({"job": "train"}, None)


def test_ssm_placeholder_means_unset(monkeypatch):
    from src import ssm

    assert ssm.get(None) is None
    fake_ssm(monkeypatch, "not-configured")
    assert ssm.get("/qgw/api-key") is None
    monkeypatch.delenv("QGW_API_KEY", raising=False)
    monkeypatch.setenv("QGW_API_KEY_PARAM", "/qgw/api-key")
    assert ssm.load_env("QGW_API_KEY", "QGW_API_KEY_PARAM") is False and "QGW_API_KEY" not in os.environ
    fake_ssm(monkeypatch, "s3cret")
    assert ssm.load_env("QGW_API_KEY", "QGW_API_KEY_PARAM") is True and os.environ["QGW_API_KEY"] == "s3cret"
    monkeypatch.delenv("QGW_API_KEY")


def test_api_hydrates_from_s3_only_when_configured(monkeypatch, tmp_path):
    from api.main import app

    seen = []
    monkeypatch.setattr(storage, "hydrate", lambda parts, dest: seen.append((parts, dest)) or [])
    monkeypatch.delenv("QGW_S3_PULL", raising=False)
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
    assert seen == []
    monkeypatch.setenv("QGW_S3_PULL", "reports/real, data/processed/real")
    monkeypatch.setenv("QGW_S3_PULL_DIR", str(tmp_path))
    with TestClient(app):
        pass
    assert seen == [(["reports/real", "data/processed/real"], tmp_path)]


@pytest.mark.parametrize(("tier", "sent"), [(3, True), (2, False), (0, False)])
def test_drift_job_emails_only_tier3(calls, monkeypatch, tier, sent):
    published = []
    sns = types.SimpleNamespace(publish=lambda **kw: published.append(kw))
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda name: sns))
    monkeypatch.setenv("QGW_ALERT_TOPIC_ARN", "arn:aws:sns:ap-southeast-2:000000000000:qglacierwatch-alerts")
    latest = aws_job.WORK / "reports" / "real" / "drift_latest.json"
    latest.parent.mkdir(parents=True)
    rec = {"tier": tier, "action": "retrain candidate", "reasons": ["QS ratio 4.10 at h7"]}
    latest.write_text(json.dumps({"check_date": "2025-12-31", "severity": "critical", "recommendation": rec}))
    out = aws_job.handler({"job": "drift"}, None)
    assert out["alert_sent"] is sent and len(published) == int(sent)
    if sent:
        assert "Tier 3" in published[0]["Subject"] and "QS ratio 4.10 at h7" in published[0]["Message"]


def test_alerts_are_a_no_op_without_a_topic(monkeypatch):
    from src import alerts

    monkeypatch.delenv("QGW_ALERT_TOPIC_ARN", raising=False)
    assert not alerts.enabled() and alerts.notify("s", "m") is False
