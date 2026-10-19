# One image, several roles (api | dashboard | job <module>), so ACR stores a single artifact.
# Build from the repository root:  docker build -f docker/Dockerfile -t qglacierwatch:dev .
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    QGW_MODE=real \
    QGW_DATA=/mnt/qgw/data \
    QGW_ARTIFACTS=/mnt/qgw/artifacts \
    QGW_REPORTS=/mnt/qgw/reports

# libgomp1: LightGBM OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src
COPY api ./api
COPY dashboard ./dashboard
COPY configs ./configs
COPY docs ./docs
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && useradd --create-home --uid 10001 qgw \
    && mkdir -p /mnt/qgw && chown -R qgw /mnt/qgw /app
USER qgw

EXPOSE 8000 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || curl -fsS http://localhost:8501/_stcore/health || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
