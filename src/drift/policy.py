"""Map drift alerts at one check to a retraining tier. Retraining is recommended only on evidence.

Tier 1  data_quality / pipeline alerts -> fix inputs; forecasting is suspended for affected sources,
        no model change (a model trained on clean data should not be refit to broken inputs).
Tier 2  persistent residual alert driven by coverage only (QS ratio below threshold) -> recalibrate.
Tier 3  persistent residual alert with QS degradation in `requires_alerts`, for at least
        `min_persistence_windows` checks -> retrain a candidate and compare with the incumbent.
Tier 4  promotion: never automatic; registry gate + named approver (src/registry).
Season-aware covariate drift alone is informational: inputs moving outside past years' range is
a reason to watch skill, not proof that the model is wrong.
"""

import pandas as pd


def recommend(alerts: pd.DataFrame, cfg_retrain: dict, qs_ratio_alert: float) -> dict:
    """alerts: rows with alert=True at one check date (season-aware and rule detectors only)."""
    if alerts.empty:
        return {"tier": 0, "action": "none", "reasons": []}
    kinds = set(alerts["kind"])
    if kinds & {"data_quality", "pipeline"}:
        bad = alerts[alerts["kind"].isin(["data_quality", "pipeline"])]["target"].tolist()
        return {"tier": 1, "action": cfg_retrain["tier1_data_quality"]["action"], "reasons": [f"input problem: {', '.join(bad)}"]}
    res = alerts[alerts["kind"] == "residual"]
    if not res.empty:
        degraded = res[res["statistic"] > qs_ratio_alert]
        if not degraded.empty:
            return {"tier": 3, "action": cfg_retrain["tier3_retrain"]["action"], "reasons": [f"QS ratio {r.statistic:.2f} at {r.target}" for r in degraded.itertuples()]}
        return {"tier": 2, "action": cfg_retrain["tier2_recalibrate"]["action"], "reasons": [f"coverage drop at {r.target}" for r in res.itertuples()]}
    cov = alerts[alerts["kind"].isin(["covariate", "prediction"])]
    return {"tier": 0, "action": "monitor: inputs outside seasonal range, skill not yet degraded", "reasons": cov["target"].tolist()}
