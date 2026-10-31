"""Read-side access to forecasts, hindcasts, registry state and monitoring reports.

Labels every forecast with how it was produced so consumers cannot mistake a hindcast for an
operational forecast:
    train_in_sample  fitted on these dates (not a skill estimate)
    calibration      used to fit conformal offsets
    test             held-out hindcast
    operational      issued from the latest available data with the production (or candidate) model
"""

import json
from datetime import UTC, datetime
from functools import lru_cache

import numpy as np
import pandas as pd

from src import config
from src.features.build import load_latest
from src.registry.registry import registry_for


class Store:
    def __init__(self, mode: str):
        self.mode = mode
        self.art = config.artifact_dir(mode)
        self.reports = config.reports_dir(mode)
        self.registry = registry_for(mode)

    # -- inputs ---------------------------------------------------------------------------
    @lru_cache(maxsize=1)  # noqa: B019 - one Store per process; cache lives as long as it does
    def features(self) -> tuple[pd.DataFrame, dict]:
        return load_latest(self.mode)

    def hindcasts(self) -> pd.DataFrame:
        path = self.art / "hindcasts.parquet"
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    def data_freshness(self) -> dict:
        table, meta = self.features()
        last_obs = table.index[table["y_h1"].notna().to_numpy()].max() + pd.Timedelta(days=1)
        today = pd.Timestamp(datetime.now(UTC).date())
        return {
            "dataset_id": meta["dataset_id"],
            "last_issue_date": str(table.index.max().date()),
            "last_observed_discharge_date": str(last_obs.date()),
            "data_age_days": int((today - last_obs).days),
            "target_source": meta["target_source"],
            "target_is_observed": meta["target_is_observed"],
        }

    # -- models ---------------------------------------------------------------------------
    def serving_model(self) -> tuple[str | None, str]:
        """Production model if one is promoted, otherwise the newest candidate (flagged)."""
        state = self.registry.list()
        if state["production"]:
            return state["production"], "production"
        cands = sorted(state["models"].items(), key=lambda kv: kv[1]["registered_utc"])
        return (cands[-1][0], "unpromoted_candidate") if cands else (None, "none")

    @lru_cache(maxsize=4)  # noqa: B019
    def _bundle(self, model_id: str) -> dict:
        return self.registry.load_bundle(model_id)

    def serving_bundle(self) -> tuple[str, str, dict]:
        """(model_id, status, bundle) of the serving model."""
        model_id, status = self.serving_model()
        if model_id is None:
            raise LookupError("No registered model. Run: python -m src.pipeline.train --final")
        return model_id, status, self._bundle(model_id)

    def operational_forecast(self, issue_date: pd.Timestamp | None = None) -> dict:
        model_id, status = self.serving_model()
        if model_id is None:
            raise LookupError("No registered model. Run: python -m src.pipeline.train --final")
        table, meta = self.features()
        issue = table.index.max() if issue_date is None else pd.Timestamp(issue_date)
        if issue not in table.index:
            raise KeyError(f"No feature row for issue date {issue.date()}")
        bundle = self._bundle(model_id)
        idx = pd.DatetimeIndex([issue])
        rows, warnings = [], []
        row = table.loc[issue]
        if row["flag_q_missing"]:
            warnings.append("latest discharge missing at issue time")
        if row["snow_age"] > 8:
            warnings.append(f"snow cover is {int(row['snow_age'])} days old (cloud/sensor gap)")
        for h in bundle["horizons"]:
            q = np.mean([m.predict(table, idx) for m in bundle["models"][h]], axis=0)
            target = issue + pd.Timedelta(days=h)
            q = bundle["cqr"][h].apply(np.sort(q, axis=1), pd.DatetimeIndex([target]))[0]
            obs = table.loc[issue, f"y_h{h}"]
            rows.append(
                {
                    "horizon_days": h,
                    "target_date": str(target.date()),
                    "p10": float(q[0]),
                    "p50": float(q[1]),
                    "p90": float(q[2]),
                    "observed": None if pd.isna(obs) else float(obs),
                }
            )
        return {
            "issue_date": str(issue.date()),
            "kind": "operational" if issue_date is None else "replay_with_serving_model",
            "model_id": model_id,
            "model_status": status,
            "model_family": bundle["family"],
            "dataset_id": meta["dataset_id"],
            "target_source": meta["target_source"],
            "target_is_observed": meta["target_is_observed"],
            "units": "m3/s",
            "interval": "P10-P90 (conformal-calibrated, nominal 80%)",
            "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "warnings": warnings,
            "forecasts": rows,
        }

    def hindcast(self, issue_date: pd.Timestamp, model: str) -> dict:
        hc = self.hindcasts()
        if hc.empty:
            raise LookupError("No hindcasts. Run the training pipeline first.")
        sel = hc[(hc["issue_date"] == pd.Timestamp(issue_date)) & (hc["model"] == model)].sort_values("h")
        if sel.empty:
            raise KeyError(f"No {model} hindcast issued on {pd.Timestamp(issue_date).date()}")
        return {
            "issue_date": str(pd.Timestamp(issue_date).date()),
            "kind": f"hindcast:{sel['split'].iloc[0]}",
            "model_family": model,
            "forecasts": [
                {
                    "horizon_days": int(r.h),
                    "target_date": str(r.target_date.date()),
                    "p10": float(r.p10),
                    "p50": float(r.p50),
                    "p90": float(r.p90),
                    "observed": None if pd.isna(r.obs) else float(r.obs),
                }
                for r in sel.itertuples()
            ],
        }

    # -- reports --------------------------------------------------------------------------
    def report(self, name: str) -> dict | None:
        path = self.reports / f"{name}.json"
        return json.loads(path.read_text()) if path.exists() else None
