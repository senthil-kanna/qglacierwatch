"""QGlacierWatch REST API (versioned under /v1).

Run locally (no Azure credentials needed):
    uvicorn api.main:app --reload            # QGW_MODE=demo for the synthetic fixture

Security: set QGW_API_KEY to require an X-API-Key header on every /v1 data route. Rate limiting is
a per-client in-memory token bucket (QGW_RATE_PER_MIN); behind several replicas use the gateway's
limiter instead (see docs/deployment.md).
"""

import json
import logging
import os
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from api.schemas import ErrorResponse, ForecastResponse, Health
from src import config
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
