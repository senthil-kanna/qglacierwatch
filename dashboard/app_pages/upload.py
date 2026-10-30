from datetime import UTC, datetime

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data
from src import config

SAMPLES = config.ROOT / "dashboard" / "samples"
LIGHTS = {
    "green": (st.success, ":material/check_circle:", "No drift: the model is fine, no retraining needed."),
    "amber": (st.warning, ":material/visibility:", "Drift or data issue, but no evidence the model is wrong: monitor (no retraining)."),
    "red": (st.error, ":material/report:", "RETRAINING NEEDED (Tier 3): inputs drifted and the model's error degraded."),
}

st.caption(
    "Upload new daily data and the weekly drift monitors run on it exactly as on the archive. The upload stays in this "
    "browser session: it is not stored, never changes the archive or the serving model, and nothing is retrained here."
)

with st.expander("File format and samples", expanded=True):
    st.markdown(
        "CSV with one row per consecutive day, at least 30 days, starting inside or right after the archive:\n\n"
        "`date, temperature_2m (deg C), precipitation (mm/day), snow_frac (0-1), discharge (m3/s)`\n\n"
        "Discharge is required: retraining is recommended only when the model's forecasts of the uploaded discharge "
        "get worse, not because inputs changed."
    )
    with st.container(horizontal=True):
        for name, label in (("normal_data.csv", "normal sample"), ("changed_data.csv", "changed sample")):
            path = SAMPLES / name
            if path.exists():
                st.download_button(f"Download {label} (SYNTHETIC)", path.read_bytes(), file_name=name, mime="text/csv", icon=":material/download:")
    st.caption("Both samples are SYNTHETIC: Jun-Jul 2025 archive values with small noise (normal) or 3 deg C warmer and altered discharge (changed).")

file = st.file_uploader("CSV file", type="csv", max_upload_size=2)
if file is None:
    st.stop()

with st.spinner("Checking the file and running the drift monitors..."):
    try:
        r = data.upload_check(file.getvalue())
    except LookupError as e:
        st.error(str(e))
        st.stop()

with st.container(border=True):
    st.subheader("1. File check")
    if r["ok"]:
        st.success(f"{r['n_days']} days, {r['window'][0]} to {r['window'][1]}: columns and values are valid.", icon=":material/task_alt:")
    for e in r["errors"]:
        st.error(e, icon=":material/error:")
    for w in r["warnings"]:
        st.warning(w, icon=":material/warning:")
    if not r["ok"]:
        st.caption(f"Archive covers {r['archive'][0]} to {r['archive'][1]}.")
        st.stop()

rec = r["recommendation"]
show, icon, text = LIGHTS[r["light"]]
with st.container(border=True):
    st.subheader("2. Decision")
    show(f"**{text}**", icon=icon)
    with st.container(horizontal=True):
        st.metric("Tier", rec["tier"], border=True)
        st.metric("Severity", r["severity"], border=True)
        st.metric("Check date", r["check_date"], border=True)
    st.markdown(f"Action: **{rec['action']}**")
    for reason in rec["reasons"]:
        st.markdown(f"- {reason}")
    st.caption(
        "Tier 0: no alert or inputs outside past seasons only | Tier 1: input problem | Tier 2: interval coverage dropped, "
        "recalibrate | Tier 3: forecast error degraded persistently, retrain a candidate. Same rules as the weekly job."
    )

with st.container(border=True):
    st.subheader("3. Evidence")
    res = r["residual"].copy()
    if not res.empty:
        res["detail"] = res["detail"].map(lambda d: d if isinstance(d, dict) else {})
        rows = pd.DataFrame(
            {
                "lead": res["target"],
                "QS ratio (window / same season before)": res["statistic"],
                "alert threshold": config.load_yaml("drift")["residual"]["qs_ratio_alert"],
                "P10-P90 coverage": res["detail"].map(lambda d: d.get("coverage_window")),
                "days": res["detail"].map(lambda d: d.get("n")),
                "alert": res["alert"],
            }
        )
        st.dataframe(rows, hide_index=True, column_config={"P10-P90 coverage": st.column_config.NumberColumn(format="%.2f"),
                                                           "QS ratio (window / same season before)": st.column_config.NumberColumn(format="%.2f")})
    alerts = r["alerts"]
    if alerts.empty:
        st.caption("No monitor raised an alert.")
    else:
        st.dataframe(alerts[["kind", "target", "statistic", "p_value"]], hide_index=True,
                     column_config={"statistic": st.column_config.NumberColumn(format="%.2f"), "p_value": st.column_config.NumberColumn(format="%.1e")})

    fc = r["forecasts"]
    lead = st.segmented_control("Forecast lead (days)", sorted(fc["h"].unique()), default=int(fc["h"].min()))
    sel = fc[fc["h"] == (lead or int(fc["h"].min()))].sort_values("target_date")
    base = alt.Chart(sel).encode(x=alt.X("target_date:T", title=None))
    band = base.mark_area(opacity=0.25, color="#4c78a8").encode(y=alt.Y("p10:Q", title="Discharge (m3/s)"), y2="p90:Q")
    p50 = base.mark_line(color="#4c78a8").encode(y="p50:Q", tooltip=["target_date:T", alt.Tooltip("p50:Q", format=".1f"), alt.Tooltip("obs:Q", format=".1f")])
    obs = base.mark_line(color="#e45756", strokeDash=[4, 2]).encode(y="obs:Q")
    st.altair_chart((band + p50 + obs).properties(height=280), width="stretch")
    st.caption(f"Blue: serving model `{r['model_id']}` ({r['model_status'].replace('_', ' ')}) P50 with P10-P90 band. Red dashed: uploaded discharge.")

if rec["tier"] == 3:
    with st.container(border=True):
        st.subheader("4. Human decision")
        st.caption(
            "Retraining starts only after a named person approves the request; a retrained candidate is then promoted only "
            "if it passes the registry gate. This demo records the decision in this session only."
        )
        log = st.session_state.setdefault("upload_decisions", [])
        with st.form("approve"):
            who = st.text_input("Approver name")
            ok = st.form_submit_button("Approve retraining request", type="primary")
        if ok:
            if who.strip():
                log.append({"time_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"), "approver": who.strip(),
                            "window": " to ".join(r["window"]), "tier": rec["tier"], "reasons": "; ".join(rec["reasons"])})
            else:
                st.warning("Enter the approver's name.")
        if log:
            st.dataframe(pd.DataFrame(log), hide_index=True)
            st.caption("Session-only record (not saved, not sent anywhere).")
