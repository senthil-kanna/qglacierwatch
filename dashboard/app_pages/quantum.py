import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data

res = data.report("quantum_benchmark")
if not res:
    st.info("Quantum benchmark not generated. Run `python -m src.quantum.benchmark`.")
    st.stop()

st.warning(res["interpretation_guardrail"], icon=":material/memory:")
st.caption(
    f"Task: {res['horizon']}-day discharge quantiles | inputs: {res['inputs']['pca_components']} PCA components "
    f"({res['inputs']['explained_variance_train']:.0%} variance) | simulator: {res['simulator']['device']} | seeds {res['protocol']['seeds']}"
)

s = pd.DataFrame(res["summary"]).T.reset_index(names="model")
s["kind"] = s["model"].map(lambda m: "quantum (simulated)" if m.startswith("vqc") else "classical")
with st.container(border=True):
    st.subheader("Test QS by model (mean and 95% CI over seeds)")
    s["lo"] = s["qs_ci95"].map(lambda c: c[0])
    s["hi"] = s["qs_ci95"].map(lambda c: c[1])
    base = alt.Chart(s).encode(y=alt.Y("model:N", sort=alt.EncodingSortField("qs_mean"), title=None))
    chart = base.mark_rule().encode(x=alt.X("lo:Q", title="QS (m3/s), lower is better"), x2="hi:Q") + base.mark_point(filled=True, size=80).encode(x="qs_mean:Q", color="kind:N")
    ref = pd.DataFrame([{"model": k, "qs": v} for k, v in res["reference_full_feature_models_qs"].items()])
    if not ref.empty:
        chart = chart + alt.Chart(ref).mark_rule(strokeDash=[4, 3], color="gray").encode(x="qs:Q", tooltip=["model", "qs"])
    st.altair_chart(chart.properties(height=280), width="stretch")
    st.caption("Grey dashed lines: full-feature models from the main experiment on the same test period, for context.")

st.dataframe(
    s[["model", "params_total", "params_circuit", "qs_mean", "qs_sd", "coverage_mean", "nse_mean", "train_seconds_mean", "circuit_forward_evals_mean", "param_shift_equiv_evals_mean"]],
    hide_index=True,
)
with st.container(border=True):
    st.subheader("Paired comparisons (VQC minus other; negative favours VQC)")
    st.dataframe(pd.DataFrame(res["comparisons"]).drop(columns=["block_bootstrap_seed_avg"], errors="ignore"), hide_index=True)
    st.caption("With 5 seeds the smallest exact two-sided Wilcoxon p-value is 0.0625.")
