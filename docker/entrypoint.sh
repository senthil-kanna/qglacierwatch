#!/bin/sh
# Roles:
#   api                     FastAPI on :8000
#   dashboard               Streamlit on :8501
#   job <python module> ... run a pipeline step, e.g. `job src.drift.replay --latest`
#   demo-setup              build the SYNTHETIC fixture, features and a quick model (no credentials)
set -e
role="${1:-api}"
shift || true
case "$role" in
  api)
    exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers ;;
  dashboard)
    exec streamlit run dashboard/streamlit_app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true ;;
  job)
    exec python -m "$@" ;;
  demo-setup)
    python -m src.data.synthetic
    python -m src.features.build --mode demo
    exec python -m src.pipeline.train --mode demo --quick --final ;;
  *)
    exec "$role" "$@" ;;
esac
