#!/bin/sh
# Roles:
#   api                     FastAPI on :8000
#   dashboard               Streamlit on :8501
#   job <python module> ... run a pipeline step, e.g. `job src.drift.replay --latest`
#   demo-setup              build the SYNTHETIC fixture, features and a quick model (no credentials)
#
# QGW_S3_BUCKET set (AWS Fargate): the dashboard pulls its inputs from S3 at start and re-pulls the
# small, job-written parts every 15 min. Unset: local filesystem only (compose, Azure Files).
# The AWS scheduled jobs do not use this script; they run src.aws_job on Lambda.
set -e
role="${1:-api}"
shift || true
DASH_PARTS="data/raw data/processed/real artifacts/real reports/real"
case "$role" in
  api)
    exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers ;;
  dashboard)
    if [ -n "$QGW_S3_BUCKET" ]; then
      python -m src.storage pull $DASH_PARTS
      (while sleep 900; do python -m src.storage pull reports/real data/processed/real || true; done) &
    fi
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
