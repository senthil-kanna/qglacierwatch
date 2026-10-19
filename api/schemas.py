from typing import Literal

from pydantic import BaseModel, Field


class HorizonForecast(BaseModel):
    horizon_days: int = Field(description="Lead time after the issue date")
    target_date: str
    p10: float = Field(ge=0, description="10th percentile discharge, m3/s")
    p50: float = Field(ge=0, description="Median discharge, m3/s")
    p90: float = Field(ge=0, description="90th percentile discharge, m3/s")
    observed: float | None = Field(None, description="Verifying discharge if already available, m3/s")


class ForecastResponse(BaseModel):
    issue_date: str
    kind: str = Field(description="operational | replay_with_serving_model | hindcast:<split>")
    model_id: str | None = None
    model_status: str | None = Field(None, description="production | unpromoted_candidate")
    model_family: str
    dataset_id: str | None = None
    target_source: str | None = None
    target_is_observed: bool | None = Field(None, description="False means the target is modelled (GloFAS), not a gauge")
    units: str = "m3/s"
    interval: str = "P10-P90 (conformal-calibrated, nominal 80%)"
    generated_utc: str | None = None
    warnings: list[str] = []
    forecasts: list[HorizonForecast]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    mode: str
    api_version: str
    model_id: str | None
    model_status: str
    freshness: dict | None
    problems: list[str]


class ErrorResponse(BaseModel):
    error: str
    detail: str
