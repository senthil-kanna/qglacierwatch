"""Retraining approval from the alert e-mail (src/approvals.py and the API pages); no AWS access."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src import approvals

REC = {"tier": 3, "action": "retrain candidate", "reasons": ["QS ratio 4.10 at h7 <b>"]}


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.delenv("QGW_S3_BUCKET", raising=False)
    monkeypatch.setenv("QGW_REPORTS", str(tmp_path / "reports"))
    monkeypatch.setenv("QGW_API_URL", "https://example.lambda-url.ap-southeast-2.on.aws/")
    return tmp_path


@pytest.fixture
def client(local, monkeypatch):
    from api import main

    monkeypatch.setattr(main, "Store", lambda mode: None)
    monkeypatch.delenv("QGW_API_KEY", raising=False)
    with TestClient(main.app) as c:
        yield c


def test_request_stores_only_the_token_hash_and_mails_a_link(local):
    req, token = approvals.create(REC, "2025-07-31", "dashboard upload")
    saved = (local / "reports" / "approvals" / f"{req['id']}.json").read_text()
    assert token not in saved and req["token_sha256"] in saved and req["status"] == "pending"
    lines = approvals.email_lines(req, token)
    assert f"https://example.lambda-url.ap-southeast-2.on.aws/v1/approvals/{req['id']}?token={token}" in lines


def test_link_opens_the_page_but_only_the_form_approves(client):
    req, token = approvals.create(REC, "2025-07-31", "dashboard upload")
    page = client.get(f"/v1/approvals/{req['id']}", params={"token": token})
    assert page.status_code == 200 and "<form method='post'" in page.text
    assert "&lt;b&gt;" in page.text and "<b>QS" not in page.text  # request text is escaped
    assert approvals.load(req["id"])["status"] == "pending"  # a mail scanner's GET approves nothing
    done = client.post(f"/v1/approvals/{req['id']}", data={"token": token, "approver": "  Dr  Rao "})
    assert done.status_code == 200 and "Approved by <b>Dr Rao</b>" in done.text
    saved = approvals.load(req["id"])
    assert saved["status"] == "approved" and saved["approver"] == "Dr Rao" and saved["approved_via"] == "e-mail link"
    again = client.post(f"/v1/approvals/{req['id']}", data={"token": token, "approver": "Someone Else"})
    assert "Dr Rao" in again.text and approvals.load(req["id"])["approver"] == "Dr Rao"


@pytest.mark.parametrize(("req_id", "token", "status"), [
    ("ok", "wrong-token", 403), ("ok", "", 403), ("0123456789abcdef", "x", 404), ("..%2F..%2Fsecrets", "x", 404),
])
def test_bad_links_are_refused(client, req_id, token, status):
    req, _ = approvals.create(REC, "2025-07-31", "dashboard upload")
    rid = req["id"] if req_id == "ok" else req_id
    assert client.get(f"/v1/approvals/{rid}", params={"token": token}).status_code == status
    assert client.post(f"/v1/approvals/{rid}", data={"token": token, "approver": "X"}).status_code == status
    assert approvals.load(req["id"])["status"] == "pending"


def test_expired_link_and_missing_name_do_not_approve(client, monkeypatch):
    req, token = approvals.create(REC, "2025-07-31", "dashboard upload")
    assert client.post(f"/v1/approvals/{req['id']}", data={"token": token, "approver": "  "}).status_code == 400
    later = datetime.now(UTC) + timedelta(hours=approvals.TTL_HOURS + 1)
    monkeypatch.setattr(approvals, "_now", lambda: later)
    assert client.post(f"/v1/approvals/{req['id']}", data={"token": token, "approver": "Dr Rao"}).status_code == 410
    assert approvals.load(req["id"])["status"] == "pending"
    assert approvals.approve_from_dashboard(req["id"], "Dr Rao")["approved_via"] == "dashboard"


def test_approval_pages_skip_the_api_key_but_data_routes_keep_it(client, monkeypatch):
    monkeypatch.setenv("QGW_API_KEY", "test-key")
    req, token = approvals.create(REC, "2025-07-31", "dashboard upload")
    assert client.get(f"/v1/approvals/{req['id']}", params={"token": token}).status_code == 200
    assert client.get("/v1/models").status_code == 401


def test_recent_lists_newest_first(local):
    a, _ = approvals.create(REC, "2025-07-01", "a")
    b, _ = approvals.create(REC, "2025-07-02", "b")
    ids = [r["id"] for r in approvals.recent()]
    assert set(ids) == {a["id"], b["id"]} and all(re.fullmatch(r"[0-9a-f]{16}", i) for i in ids)
