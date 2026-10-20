import json

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data
from src import config

res = data.report("drift_replay")
path = config.artifact_dir(config.mode()) / "drift_findings.parquet"
if not res or not path.exists():
    st.info("Drift replay not generated. Run `python -m src.drift.replay`.")
    st.stop()

st.caption(res["note"])
f = pd.read_parquet(path)
f["check_date"] = pd.to_datetime(f["check_date"])

rows = [{"monitor": k.replace("|", " / "), **{x: v[x] for x in ("checks_evaluated", "checks_with_alert", "alert_rate")}} for k, v in res["replay"]["by_detector"].items()]
with st.container(border=True):
    st.subheader("Historical replay: alert rates by monitor")
    st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={"alert_rate": st.column_config.ProgressColumn("Alert rate", min_value=0, max_value=1, format="%.3f")})
    st.caption("Baseline = season-blind KS against the previous 365 days. Season-aware = same calendar window in past years. Same FDR and persistence rules.")

with st.container(border=True):
    st.subheader("Alert timeline")
    kinds = st.pills("Monitors", ["covariate", "prediction", "residual", "data_quality", "pipeline"], selection_mode="multi", default=["covariate", "residual", "data_quality", "pipeline"])
    a = f[f["alert"] & f["kind"].isin(kinds or [])]
    a = a.assign(monitor=a["kind"] + " / " + a["detector"])
    chart = alt.Chart(a).mark_tick(thickness=2).encode(x=alt.X("check_date:T", title=None), y=alt.Y("monitor:N", title=None), color="kind:N", tooltip=["check_date:T", "target", "statistic", "p_value"])
    events = pd.DataFrame(res["documented_events"])
    if not events.empty:
        events["start"] = pd.to_datetime(events["start"])
        chart = chart + alt.Chart(events).mark_rule(strokeDash=[3, 3], color="gray").encode(x="start:T", tooltip=["label"])
    st.altair_chart(chart.properties(height=260), width="stretch")
    st.caption("Dashed: documented real event (context only, not a drift label).")

with st.container(border=True):
    st.subheader("Controlled synthetic perturbations")
    st.caption("SYNTHETIC events injected into copies of the real inputs. These are not real climate events.")
    srows = []
    for kind, r in res.get("synthetic", {}).items():
        for det, s in r["summary"].items():
            srows.append({"event": kind, "detector": det, "recall": s["recall"], "median delay (d)": s["median_delay_days"], "missed": s["missed"], "clean windows with alarm": s["clean_windows_with_alarm"], "event precision": s["precision_event_level"]})
    st.dataframe(pd.DataFrame(srows), hide_index=True)

with st.container(border=True):
    st.subheader("Recommended actions (season-aware and rule monitors)")
    dec = pd.DataFrame(res["decisions"])
    if dec.empty:
        st.caption("No alerts.")
    else:
        st.dataframe(dec.iloc[::-1], hide_index=True)

with st.expander("Raw findings for one check"):
    d = st.selectbox("Check date", sorted(f["check_date"].dt.date.unique(), reverse=True))
    one = f[f["check_date"].dt.date == d].copy()
    one["detail"] = one["detail"].map(lambda s: json.loads(s) if isinstance(s, str) else s)
    st.dataframe(one, hide_index=True)
