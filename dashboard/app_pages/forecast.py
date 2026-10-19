import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data

data.provenance_banner()
table, meta = data.features()
fresh = data.store().data_freshness()
op = data.operational()

with st.container(horizontal=True):
    st.metric("Last observed discharge date", fresh["last_observed_discharge_date"], border=True)
    st.metric("Data age", f"{fresh['data_age_days']} days", border=True)
    st.metric("Serving model", op["model_family"] if op else "none", border=True)
    st.metric("Model status", op["model_status"].replace("_", " ") if op else "no model", border=True)

if fresh["data_age_days"] > 30:
    st.warning(
        f"Inputs end on {fresh['last_observed_discharge_date']}. The forecast below is issued from the latest "
        "available data and is not a current forecast.",
        icon=":material/schedule:",
    )

with st.container(border=True):
    st.subheader("Forecast from latest available data")
    if op is None:
        st.info("No registered model yet. Run `python -m src.pipeline.train --final`.")
    else:
        if op["model_status"] != "production":
            st.caption(":orange[Served by an unpromoted candidate: it did not pass, or has not been through, the promotion gate.]")
        rows = pd.DataFrame(op["forecasts"])
        rows = rows.rename(columns={"horizon_days": "lead (days)", "target_date": "target date"})
        st.dataframe(
            rows[["lead (days)", "target date", "p10", "p50", "p90"]],
            hide_index=True,
            column_config={c: st.column_config.NumberColumn(f"{c.upper()} (m3/s)", format="%.1f") for c in ("p10", "p50", "p90")},
        )
        st.caption(
            f"Issued {op['issue_date']} | generated {op['generated_utc']} | model `{op['model_id']}` | dataset "
            f"`{op['dataset_id']}` | {op['interval']}"
        )
        for w in op["warnings"]:
            st.warning(w, icon=":material/warning:")

st.subheader("Historical replay")
hc = data.hindcasts()
if hc.empty:
    st.info("No hindcasts stored. Run the training pipeline.")
    st.stop()

with st.container(horizontal=True):
    model = st.selectbox("Model", sorted(hc["model"].unique()), index=sorted(hc["model"].unique()).index("gbm_quantile"))
    h = st.segmented_control("Lead time (days)", [1, 7, 30], default=7)
    split = st.segmented_control(
        "Period", ["test", "calibration", "train_in_sample"], default="test", format_func=lambda s: s.replace("_", " ")
    )
h = h or 7
split = split or "test"
sel = hc[(hc["model"] == model) & (hc["h"] == h) & (hc["split"] == split)].sort_values("target_date")
lo, hi = sel["target_date"].min().date(), sel["target_date"].max().date()
window = st.slider("Verification window", min_value=lo, max_value=hi, value=(max(lo, hi - pd.Timedelta(days=365).to_pytimedelta()), hi))
view = sel[(sel["target_date"].dt.date >= window[0]) & (sel["target_date"].dt.date <= window[1])]
st.caption(data.SPLIT_LABELS[split])

base = alt.Chart(view).encode(x=alt.X("target_date:T", title="Target date"))
band = base.mark_area(opacity=0.25).encode(
    y=alt.Y("p10:Q", title="Discharge (m3/s)"), y2="p90:Q", tooltip=["target_date:T", "p10:Q", "p50:Q", "p90:Q", "obs:Q"]
)
median = base.mark_line().encode(y="p50:Q", color=alt.value("#1f77b4"))
obs = base.mark_line(strokeDash=[4, 2]).encode(y="obs:Q", color=alt.value("#222222"))
st.altair_chart((band + median + obs).properties(height=380), width="stretch")
st.caption(f"Shaded: P10-P90 (calibrated). Solid: P50. Dashed: {meta['target_source']} on the target date. Lead {h} days.")

from src.evaluate.metrics import score_all  # noqa: E402

s = score_all(view["obs"], view[["p10", "p50", "p90"]].to_numpy())
with st.container(horizontal=True):
    st.metric("Samples", s["n"], border=True)
    st.metric("NSE (P50)", f"{s['nse']:.3f}", border=True)
    st.metric("QS (m3/s)", f"{s['qs']:.2f}", border=True)
    st.metric("P10-P90 coverage", f"{s['coverage_80']:.2f}", help="Nominal 0.80", border=True)
