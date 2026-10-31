"""Retraining requests that a named person approves, from the alert e-mail or the dashboard.

A Tier 3 alert creates a request and e-mails a one-time link to the API:
    <QGW_API_URL>/v1/approvals/<id>?token=<token>
Opening the link only shows the request (mail scanners prefetch links); approval needs a name and
a POST from the form on that page. Only the token's SHA-256 is stored, the link expires after
TTL_HOURS and an approved request cannot be approved again.

Requests are JSON objects under reports/approvals/ in the S3 bucket (QGW_S3_BUCKET), or in the
local reports root without one. Approval only records the decision; retraining is still started
by a person and a candidate is promoted only through the registry gate.
"""

import hashlib
import json
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src import storage

PREFIX = "reports/approvals"
TTL_HOURS = 48
ID_RE = re.compile(r"^[0-9a-f]{16}$")


class ApprovalError(Exception):
    """Request cannot be approved; `status` is the HTTP status the API answers with."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S UTC")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _local(req_id: str) -> Path:
    return storage.local_dir(PREFIX) / f"{req_id}.json"


def _save(req: dict) -> None:
    body = json.dumps(req, indent=2)
    if b := storage.bucket():
        import boto3

        boto3.client("s3").put_object(Bucket=b, Key=f"{PREFIX}/{req['id']}.json", Body=body.encode(), ContentType="application/json")
        return
    path = _local(req["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def load(req_id: str) -> dict | None:
    if not ID_RE.match(req_id or ""):
        return None
    if b := storage.bucket():
        import boto3

        s3 = boto3.client("s3")
        try:
            return json.loads(s3.get_object(Bucket=b, Key=f"{PREFIX}/{req_id}.json")["Body"].read())
        except s3.exceptions.NoSuchKey:
            return None
    path = _local(req_id)
    return json.loads(path.read_text()) if path.exists() else None


def recent(limit: int = 20) -> list[dict]:
    """Newest requests first."""
    if b := storage.bucket():
        import boto3

        s3 = boto3.client("s3")
        keys = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=PREFIX + "/")
                for o in page.get("Contents", []) if o["Key"].endswith(".json")]
        reqs = [json.loads(s3.get_object(Bucket=b, Key=k)["Body"].read()) for k in keys]
    else:
        d = storage.local_dir(PREFIX)
        reqs = [json.loads(p.read_text()) for p in d.glob("*.json")] if d.exists() else []
    return sorted(reqs, key=lambda r: r["created_utc"], reverse=True)[:limit]


def create(rec: dict, check_date: str, source: str) -> tuple[dict, str]:
    """Store a pending request for a Tier 3 recommendation. Returns (request, token)."""
    token, now = secrets.token_urlsafe(32), _now()
    req = {
        "id": secrets.token_hex(8),
        "status": "pending",
        "created_utc": _stamp(now),
        "expires_utc": _stamp(now + timedelta(hours=TTL_HOURS)),
        "source": source,
        "check_date": check_date,
        "tier": rec["tier"],
        "action": rec["action"],
        "reasons": list(rec["reasons"]),
        "token_sha256": _digest(token),
        "approver": None,
        "approved_utc": None,
        "approved_via": None,
    }
    _save(req)
    return req, token


def link(req_id: str, token: str) -> str | None:
    """The approval page on the API, or None when QGW_API_URL is not set (local runs)."""
    base = os.getenv("QGW_API_URL")
    return f"{base.rstrip('/')}/v1/approvals/{req_id}?token={token}" if base else None


def email_lines(req: dict, token: str) -> list[str]:
    url = link(req["id"], token)
    if not url:
        return [f"Request {req['id']}: approve it on the dashboard."]
    return [
        "",
        f"Approve retraining request {req['id']} (link valid until {req['expires_utc']}, single use):",
        url,
        "The page shows the request; approval needs your name and a click on Approve. Do not forward this e-mail.",
    ]


def check_token(req_id: str, token: str) -> dict:
    """The request if `token` opens it; raises ApprovalError otherwise. Expiry is checked on approve."""
    req = load(req_id)
    if req is None:
        raise ApprovalError(404, "Unknown retraining request.")
    if not token or not secrets.compare_digest(_digest(token), req["token_sha256"]):
        raise ApprovalError(403, "This approval link is not valid.")
    return req


def _record(req: dict, approver: str, via: str) -> dict:
    approver = " ".join(approver.split())[:80]
    if not approver:
        raise ApprovalError(400, "Enter the approver's name.")
    if req["status"] == "approved":
        return req
    req.update(status="approved", approver=approver, approved_utc=_stamp(_now()), approved_via=via)
    _save(req)
    return req


def approve_with_token(req_id: str, token: str, approver: str) -> dict:
    req = check_token(req_id, token)
    if req["status"] != "approved" and _now() > datetime.strptime(req["expires_utc"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=UTC):
        raise ApprovalError(410, "This approval link has expired; approve the request on the dashboard.")
    return _record(req, approver, "e-mail link")


def approve_from_dashboard(req_id: str, approver: str) -> dict:
    req = load(req_id)
    if req is None:
        raise ApprovalError(404, "Unknown retraining request.")
    return _record(req, approver, "dashboard")
