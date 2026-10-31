import json

import pandas as pd
import streamlit as st

from dashboard import data
from src import approvals

state = data.store().registry.list()
prod = state["production"]
with st.container(horizontal=True):
    st.metric("Production model", prod or "none approved", border=True)
    st.metric("Registered models", len(state["models"]), border=True)

if state["models"]:
    st.subheader("Registry")
    st.dataframe(pd.DataFrame.from_dict(state["models"], orient="index").rename_axis("model_id").reset_index(), hide_index=True)

    model_id = st.selectbox("Inspect model card", list(state["models"]))
    card = data.store().registry.card(model_id)
    with st.container(border=True):
        st.markdown(f"**{card['model_family']}** | dataset `{card['dataset_id']}` | code `{card['git_sha']}` | stage **{card['stage']}**")
        st.markdown(f"Train {card['train_period']} | calibration {card['calibration_period']} | target `{card['target_source']}`")
        ev = pd.DataFrame(card["eval"]["by_horizon"]).T[["n", "nse", "qs", "qs_climatology", "coverage_80"]]
        st.dataframe(ev)

audit = data.store().registry.audit
if audit.exists():
    st.subheader("Audit log (promotion decisions, gates, rollbacks)")
    events = [json.loads(line) for line in audit.read_text().splitlines()]
    st.dataframe(pd.DataFrame(events).iloc[::-1], hide_index=True)

st.subheader("Retraining requests (Tier 3 alerts)")
reqs = approvals.recent()
if reqs:
    cols = ["id", "status", "created_utc", "source", "check_date", "approver", "approved_utc", "approved_via"]
    st.dataframe(pd.DataFrame(reqs)[cols], hide_index=True)
    st.caption("Each request is approved by a named person, from the one-time link in the alert e-mail or on the upload page.")
else:
    st.caption("No retraining requests yet.")

st.subheader("Retraining runs")
runs_path = data.store().reports / "retraining_runs.json"
if runs_path.exists():
    runs = pd.DataFrame(json.loads(runs_path.read_text()))
    st.dataframe(runs[["ts", "tier", "reason", "incumbent", "candidate", "eval_window", "incumbent_mean_qs", "candidate_mean_qs", "gate_passed", "promoted"]], hide_index=True)
    st.caption("Candidates are never promoted automatically; promotion needs the gate and a named approver.")
else:
    st.caption("No retraining runs executed yet.")
