import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data

data.provenance_banner()
res = data.report("forecast_results")
if not res or "test_period" not in res:
    st.info("Held-out results not generated. Run `python -m src.pipeline.train --final`.")
    st.stop()

meta = res["meta"]
st.caption(f"Dataset `{meta['dataset_id']}` | code `{meta['git_sha']}` | run {meta['generated_utc']} | seeds {meta['seeds']}")

rows = []
for r in res["test_period"].values():
    c = r["calibrated"]
    rows.append({"model": r["model"], "lead": r["h"], **{k: c[k] for k in ("n", "nse", "kge", "mae", "rmse", "qs", "coverage_80", "width_80")}, "raw coverage": r["raw"]["coverage_80"]})
df = pd.DataFrame(rows)

with st.container(border=True):
    st.subheader("Held-out test period, 2023-2025")
    st.dataframe(df, hide_index=True, column_config={c: st.column_config.NumberColumn(format="%.3f") for c in ("nse", "kge", "coverage_80", "raw coverage")})
    st.caption("QS: mean of 2x pinball loss at P10/P50/P90 (3-point CRPS approximation, m3/s). Coverage nominal 0.80.")

col1, col2 = st.columns(2)
with col1, st.container(border=True):
    st.subheader("QS by lead time")
    st.altair_chart(
        alt.Chart(df).mark_line(point=True).encode(x=alt.X("lead:O", title="Lead (days)"), y=alt.Y("qs:Q", title="QS (m3/s)"), color="model:N"),
        width="stretch",
    )
with col2, st.container(border=True):
    st.subheader("Interval coverage")
    rule = alt.Chart(pd.DataFrame({"y": [0.8]})).mark_rule(strokeDash=[4, 4]).encode(y="y:Q")
    points = alt.Chart(df).mark_circle(size=90).encode(
        x=alt.X("lead:O", title="Lead (days)"),
        y=alt.Y("coverage_80:Q", title="P10-P90 coverage", scale=alt.Scale(domain=[0.3, 1])),
        color="model:N",
    )
    st.altair_chart(points + rule, width="stretch")
    st.caption("Dashed line: nominal 0.80.")

seasonal = []
for r in res["test_period"].values():
    for season, v in r["seasonal_calibrated"].items():
        seasonal.append({"model": r["model"], "lead": r["h"], "season": season, "qs": v["qs"], "coverage": v["coverage_80"], "n": v["n"]})
sdf = pd.DataFrame(seasonal)
with st.container(border=True):
    st.subheader("Seasonal skill (by target month)")
    lead = st.segmented_control("Lead (days)", [1, 7, 30], default=7, key="skill_lead") or 7
    st.altair_chart(
        alt.Chart(sdf[sdf["lead"] == lead])
        .mark_bar()
        .encode(x=alt.X("season:N", sort=["winter", "pre_monsoon", "monsoon", "post_monsoon"]), xOffset="model:N", y=alt.Y("qs:Q", title="QS (m3/s)"), color="model:N", tooltip=["model", "season", "qs", "coverage", "n"]),
        width="stretch",
    )

with st.container(border=True):
    st.subheader("Paired block-bootstrap comparisons")
    st.dataframe(pd.DataFrame(res["comparisons"])[["h", "a", "b", "mean_diff", "lo", "hi", "p_a_better", "n"]], hide_index=True)
    st.caption("Mean QS difference A - B on identical issue dates; negative means A is better. 30-day blocks, 95% CI.")
