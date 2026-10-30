"""QGlacierWatch dashboard.

    streamlit run dashboard/streamlit_app.py            # QGW_MODE=demo for the synthetic fixture
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for `src` and `dashboard`

import streamlit as st  # noqa: E402

st.set_page_config(page_title="QGlacierWatch", page_icon=":material/water:", layout="wide")

page = st.navigation(
    {
        "Forecasts": [
            st.Page("app_pages/forecast.py", title="Forecast and replay", icon=":material/water:", default=True),
            st.Page("app_pages/skill.py", title="Skill and calibration", icon=":material/analytics:"),
        ],
        "Basin": [
            st.Page("app_pages/basin.py", title="Basin, snow and weather", icon=":material/landscape:"),
            st.Page("app_pages/lakes.py", title="Glacial lakes", icon=":material/waves:"),
        ],
        "Operations": [
            st.Page("app_pages/drift.py", title="Drift monitoring", icon=":material/monitor_heart:"),
            st.Page("app_pages/upload.py", title="Upload and check", icon=":material/upload_file:"),
            st.Page("app_pages/governance.py", title="Models and retraining", icon=":material/verified:"),
            st.Page("app_pages/quantum.py", title="Quantum benchmark", icon=":material/memory:"),
        ],
    },
    position="top",
)
st.title(page.title)
page.run()
