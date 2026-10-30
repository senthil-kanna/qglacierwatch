"""Cached loaders shared by dashboard pages. All reads go through src.serving.store."""

import json

import pandas as pd
import streamlit as st

from src import config
from src.serving.store import Store

SPLIT_LABELS = {
    "train_in_sample": "In-sample fit (training dates, not a skill estimate)",
    "calibration": "Calibration period (used to fit conformal offsets)",
    "test": "Held-out hindcast (test period)",
}


@st.cache_resource
def store() -> Store:
    return Store(config.mode())


@st.cache_data(ttl="10m")
def features() -> tuple[pd.DataFrame, dict]:
    return store().features()


@st.cache_data(ttl="10m")
def hindcasts() -> pd.DataFrame:
    return store().hindcasts()


@st.cache_data(ttl="10m")
def report(name: str) -> dict | None:
    return store().report(name)


@st.cache_data(ttl="10m")
def operational() -> dict | None:
    try:
        return store().operational_forecast()
    except (LookupError, FileNotFoundError):
        return None


@st.cache_data(ttl="1h")
def basin_geojson() -> dict | None:
    path = config.raw_dir("real") / "basin.geojson"
    return json.loads(path.read_text()) if path.exists() and config.mode() == "real" else None


@st.cache_data(ttl="1h")
def snow_maps() -> pd.DataFrame | None:
    from src.ingest.snow_maps import OUT_NAME

    path = config.raw_dir("real") / OUT_NAME
    return pd.read_parquet(path) if path.exists() and config.mode() == "real" else None


@st.cache_data(ttl="10m")
def raw_daily() -> pd.DataFrame:
    from src.features.build import load_raw, merge_daily

    frames = load_raw(config.mode())
    start = min(f["date"].min() for f in frames.values())
    end = max(f["date"].max() for f in frames.values())
    return merge_daily(frames, str(start.date()), str(end.date()))


@st.cache_data(ttl="10m", max_entries=20, show_spinner=False)
def upload_check(content: bytes) -> dict:
    """Drift check on uploaded CSV bytes; same file -> same (cached) result. Nothing is persisted."""
    import io

    from src.drift.upload import check

    try:
        raw = pd.read_csv(io.BytesIO(content), comment="#")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as e:
        return {"ok": False, "errors": [f"not a readable CSV file: {e}"], "warnings": []}
    model_id, status, bundle = store().serving_bundle()
    return {**check(raw, config.mode(), bundle, model_id), "model_status": status}


def provenance_banner() -> None:
    _, meta = features()
    if config.mode() == "demo":
        st.warning("DEMO MODE: all values come from a SYNTHETIC fixture, not observations.", icon=":material/science:")
    elif not meta["target_is_observed"]:
        st.info(
            f"Target discharge is **{meta['target_source']}**: modelled GloFAS v4 discharge (reanalysis to 2023-08-04, forecast-derived after), not gauge observations. "
            "Skill shown here is skill at reproducing GloFAS. Nothing on this dashboard is a live feed.",
            icon=":material/info:",
        )
