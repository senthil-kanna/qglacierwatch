"""AWS Lambda entry point for the scheduled jobs (full container image, `awslambdaric`).

Each run starts from an empty /tmp: pull the parts the job reads from S3, run the pipeline module
unchanged, then push only the files it created or changed. EventBridge Scheduler sends
{"job": "refresh"} or {"job": "drift"}.

refresh runs the full Earth Engine + GloFAS ingest only when a real service-account key is stored
in SSM (QGW_EE_KEY_PARAM); with the placeholder it rebuilds features and drift from the raw data
already in S3 (--skip-ingest). {"skip_ingest": true} forces the latter.

drift e-mails the alert topic when the check recommends Tier 3 (retraining); lower tiers stay on
the dashboard only.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from src import alerts, ssm, storage

WORK = Path(os.getenv("QGW_JOB_DIR", "/tmp/qgw"))
_READS = ["data/raw", "data/processed/real", "artifacts/real/hindcasts.parquet", "reports/real"]
JOBS: dict[str, dict] = {
    "refresh": {"module": "src.pipeline.refresh", "args": [], "pull": _READS,
                "push": ["data/raw", "data/processed/real", "reports/real"]},
    "drift": {"module": "src.drift.replay", "args": ["--mode", "real", "--latest"], "pull": _READS,
              "push": ["reports/real"]},
}


def ee_key() -> str | None:
    """The Earth Engine key from SSM, or None while the parameter holds a placeholder."""
    value = ssm.get(os.getenv("QGW_EE_KEY_PARAM"))
    return value if value and value.startswith("{") else None


def run(job: str, skip_ingest: bool = False) -> dict:
    spec = JOBS[job]
    for name, var in storage.ROOT_ENV.items():
        os.environ[var] = str(WORK / name)
    os.environ.setdefault("QGW_MODE", "real")
    args = list(spec["args"])
    env = dict(os.environ)
    if job == "refresh":
        key = None if skip_ingest else ee_key()
        if key:
            env["EE_SERVICE_ACCOUNT_JSON"] = key
        else:
            args.append("--skip-ingest")
    storage.pull(spec["pull"])
    before = storage.snapshot(spec["push"])
    cmd = [sys.executable, "-m", spec["module"], *args]
    print("$ " + " ".join(cmd[1:]), flush=True)
    code = subprocess.run(cmd, env=env, check=False).returncode
    # A failed step may leave half-written outputs, so S3 keeps the last good copy.
    pushed = storage.push(spec["push"], since=before) if code == 0 else 0
    result = {"job": job, "args": args, "exit_code": code, "files_pushed": pushed}
    if code == 0 and job == "drift":
        result["alert_sent"] = notify_drift(WORK / "reports" / "real" / "drift_latest.json")
    print(json.dumps(result), flush=True)
    if code != 0:
        raise RuntimeError(f"{spec['module']} exited with {code}; see the log above")
    return result


def notify_drift(path: Path) -> bool:
    """E-mail a Tier 3 recommendation from the operational drift check."""
    if not path.exists():
        return False
    latest = json.loads(path.read_text())
    rec = latest["recommendation"]
    if rec["tier"] != 3:
        return False
    subject, body = alerts.drift_message(rec, latest["check_date"], "weekly drift job (real data)", [f"Severity: {latest['severity']}"])
    return alerts.notify(subject, body)


def handler(event, _context) -> dict:
    event = event or {}
    job = event.get("job")
    if job not in JOBS:
        raise ValueError(f"event.job must be one of {sorted(JOBS)}, got {job!r}")
    return run(job, skip_ingest=bool(event.get("skip_ingest")))
