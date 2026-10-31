"""QGlacierWatch REST API (versioned under /v1).

Run locally (no Azure credentials needed):
    uvicorn api.main:app --reload            # QGW_MODE=demo for the synthetic fixture

Security: set QGW_API_KEY to require an X-API-Key header on every /v1 data route. Rate limiting is
a per-client in-memory token bucket (QGW_RATE_PER_MIN); behind several replicas use the gateway's
limiter instead (see docs/deployment.md).
"""

import html
import json
import logging
import os
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader

from api.schemas import ErrorResponse, ForecastResponse, Health
from src import approvals, config, ssm, storage
from src.serving.store import Store

API_VERSION = "1.0.0"
MODELS = ("persistence", "climatology", "gbm_quantile", "quantile_lstm")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"ts": self.formatTime(record), "level": record.levelname, "msg": record.getMessage()}
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


log = logging.getLogger("qgw.api")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    log.addHandler(h)
    log.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # AWS Lambda: refresh small, frequently rewritten parts (reports, features) from S3 into /tmp;
    # the model and a fallback copy of everything are baked into the image.
    # AWS: the optional API key lives in SSM (QGW_API_KEY_PARAM); a placeholder keeps the API open.
    ssm.load_env("QGW_API_KEY", "QGW_API_KEY_PARAM")
    if os.getenv("QGW_S3_PULL"):
        parts = [x.strip() for x in os.environ["QGW_S3_PULL"].split(",") if x.strip()]
        storage.hydrate(parts, Path(os.getenv("QGW_S3_PULL_DIR", "/tmp/qgw")))
    app.state.store = Store(config.mode())
    app.state.buckets = defaultdict(lambda: [float(os.getenv("QGW_RATE_PER_MIN", "60")), time.monotonic()])
    yield


app = FastAPI(
    title="QGlacierWatch API",
    version=API_VERSION,
    description="Probabilistic discharge forecasts (P10/P50/P90) for the Beas above Bhuntar, with provenance.",
    lifespan=lifespan,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def guard(request: Request, key: Annotated[str | None, Depends(api_key_header)]) -> None:
    expected = os.getenv("QGW_API_KEY")
    if expected and not (key and secrets.compare_digest(key, expected)):
        raise HTTPException(401, "missing or invalid X-API-Key")
    rate_limit(request)


def rate_limit(request: Request) -> None:
    rate = float(os.getenv("QGW_RATE_PER_MIN", "60"))
    client = request.client.host if request.client else "unknown"
    bucket = request.app.state.buckets[client]
    now = time.monotonic()
    bucket[0] = min(rate, bucket[0] + (now - bucket[1]) * rate / 60.0)
    bucket[1] = now
    if bucket[0] < 1:
        raise HTTPException(429, "rate limit exceeded")
    bucket[0] -= 1


def store(request: Request) -> Store:
    return request.app.state.store


@app.middleware("http")
async def access_log(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    rec = logging.LogRecord("qgw.api", logging.INFO, "", 0, "request", None, None)
    rec.extra_fields = {
        "path": request.url.path,
        "method": request.method,
        "status": response.status_code,
        "ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    log.handle(rec)
    return response


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    names = {400: "bad_request", 401: "unauthorized", 404: "not_found", 429: "rate_limited", 503: "unavailable"}
    return JSONResponse(status_code=exc.status_code, content={"error": names.get(exc.status_code, "error"), "detail": str(exc.detail)})


@app.get("/health", response_model=Health, tags=["ops"])
@app.get("/v1/health", response_model=Health, tags=["ops"])
def health(s: Annotated[Store, Depends(store)]) -> Health:
    problems, fresh = [], None
    try:
        fresh = s.data_freshness()
        if fresh["data_age_days"] > 30:
            problems.append(f"discharge data is {fresh['data_age_days']} days old; forecasts are not current")
    except FileNotFoundError:
        problems.append("no processed dataset; run python -m src.features.build")
    model_id, status = s.serving_model()
    if model_id is None:
        problems.append("no registered model")
    elif status != "production":
        problems.append("serving an unpromoted candidate (no approved production model)")
    return Health(
        status="ok" if model_id and fresh else "degraded",
        mode=s.mode,
        api_version=API_VERSION,
        model_id=model_id,
        model_status=status,
        freshness=fresh,
        problems=problems,
    )


@app.get("/v1/forecast", response_model=ForecastResponse, tags=["forecast"], dependencies=[Depends(guard)])
def forecast(
    s: Annotated[Store, Depends(store)],
    issue_date: Annotated[date | None, Query(description="Omit for the latest operational forecast")] = None,
) -> dict:
    """P10/P50/P90 for 1, 7 and 30 days from the serving model."""
    try:
        return s.operational_forecast(issue_date)
    except KeyError as e:  # KeyError subclasses LookupError, so it must be caught first
        raise HTTPException(404, str(e).strip("'\"")) from e
    except LookupError as e:
        raise HTTPException(503, str(e)) from e


@app.get("/v1/hindcast", response_model=ForecastResponse, tags=["forecast"], dependencies=[Depends(guard)])
def hindcast(
    s: Annotated[Store, Depends(store)],
    issue_date: Annotated[date, Query()],
    model: Annotated[str, Query(pattern="^(" + "|".join(MODELS) + ")$")] = "gbm_quantile",
) -> dict:
    """Stored hindcast from the evaluation run, labelled with its split (train_in_sample, calibration, test)."""
    try:
        return s.hindcast(issue_date, model)
    except KeyError as e:  # KeyError subclasses LookupError, so it must be caught first
        raise HTTPException(404, str(e).strip("'\"")) from e
    except LookupError as e:
        raise HTTPException(503, str(e)) from e


@app.get("/v1/models", tags=["governance"], dependencies=[Depends(guard)])
def models(s: Annotated[Store, Depends(store)]) -> dict:
    return s.registry.list()


@app.get("/v1/reports/{name}", tags=["reports"], dependencies=[Depends(guard)])
def report(name: str, s: Annotated[Store, Depends(store)]) -> dict:
    allowed = {"forecast_results", "drift_replay", "quantum_benchmark", "lake_analysis"}
    if name not in allowed:
        raise HTTPException(404, f"unknown report {name!r}; one of {sorted(allowed)}")
    r = s.report(name)
    if r is None:
        raise HTTPException(404, f"report {name!r} has not been generated in {s.mode} mode")
    return r


# --- Retraining approval from the alert e-mail (src/approvals.py) -------------------------------
# HTML pages, not JSON: they are opened from a mail client. The one-time token in the link is the
# credential (no X-API-Key: a mail link cannot send headers). GET only shows the request, because
# mail scanners prefetch links; approval is the form's POST with the approver's name.

def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta name='referrer' content='no-referrer'><title>{html.escape(title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "input,button{font-size:1rem;padding:.5rem;margin:.25rem 0}button{cursor:pointer}"
        ".ok{color:#1a7f37}.err{color:#cf222e}</style></head>"
        f"<body><h1>{html.escape(title)}</h1>{body}</body></html>"
    )
    return HTMLResponse(doc, status_code=status, headers={"Cache-Control": "no-store"})


def _summary(req: dict) -> str:
    e = html.escape
    reasons = "".join(f"<li>{e(r)}</li>" for r in req["reasons"])
    return (
        f"<p>Request <code>{e(req['id'])}</code> from {e(req['source'])}, check date {e(req['check_date'])}.</p>"
        f"<p><b>Tier {e(str(req['tier']))}: {e(req['action'])}</b></p><ul>{reasons}</ul>"
    )


def _approved(req: dict) -> str:
    e = html.escape
    return (f"<p class='ok'>Approved by <b>{e(req['approver'])}</b> at {e(req['approved_utc'])} ({e(req['approved_via'])}).</p>"
            "<p>Retraining can now be started; a candidate is promoted only if it passes the registry gate.</p>")


@app.get("/v1/approvals/{req_id}", response_class=HTMLResponse, tags=["governance"], dependencies=[Depends(rate_limit)])
def approval_page(req_id: str, token: str = "") -> HTMLResponse:
    try:
        req = approvals.check_token(req_id, token)
    except approvals.ApprovalError as e:
        return _page("Retraining request", f"<p class='err'>{html.escape(str(e))}</p>", e.status)
    if req["status"] == "approved":
        return _page("Retraining request", _summary(req) + _approved(req))
    form = (
        f"<form method='post' action='/v1/approvals/{html.escape(req['id'])}'>"
        f"<input type='hidden' name='token' value='{html.escape(token)}'>"
        "<label>Your name<br><input name='approver' required maxlength='80' autocomplete='name'></label><br>"
        "<button type='submit'>Approve retraining request</button></form>"
        f"<p>Link valid until {html.escape(req['expires_utc'])}. Approving only records the decision.</p>"
    )
    return _page("Approve retraining?", _summary(req) + form)


@app.post("/v1/approvals/{req_id}", response_class=HTMLResponse, tags=["governance"], dependencies=[Depends(rate_limit)])
async def approval_submit(req_id: str, request: Request) -> HTMLResponse:
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    token, approver = form.get("token", [""])[0], form.get("approver", [""])[0]
    try:
        req = approvals.approve_with_token(req_id, token, approver)
    except approvals.ApprovalError as e:
        return _page("Retraining request", f"<p class='err'>{html.escape(str(e))}</p>", e.status)
    log.info("retraining request approved", extra={"extra_fields": {"request": req["id"], "via": req["approved_via"]}})
    return _page("Retraining request approved", _summary(req) + _approved(req))
