# Architecture and data flow

## Components

```mermaid
flowchart LR
    subgraph Sources
        GEE[(Google Earth Engine<br/>MOD10A1, ERA5-Land,<br/>S1 GRD, S2 L2A, GLO-30, JRC GSW)]
        OM[(Open-Meteo Flood API<br/>GloFAS v4 seamless)]
        GAUGE[(optional gauge CSV)]
    end
    subgraph Jobs["Batch jobs (Container Apps Jobs / local CLI)"]
        ING[src.ingest<br/>earth_engine, discharge]
        PROV[src.ingest.provenance<br/>SHA-256 manifest]
        FEAT[src.features.build<br/>versioned feature table]
        TRAIN[src.pipeline.train<br/>CV, fit, CQR, test]
        DRIFT[src.drift.replay<br/>monitors + policy]
        RETRAIN[src.pipeline.retrain<br/>tier 2/3 candidates]
        LAKES[src.lakes.pipeline]
        QB[src.quantum.benchmark]
    end
    subgraph Store["Shared storage (Azure Files / local disk)"]
        RAW[(data/raw<br/>immutable)]
        PROC[(data/processed/&lt;mode&gt;)]
        ART[(artifacts/&lt;mode&gt;<br/>registry, hindcasts, findings)]
        REP[(reports/&lt;mode&gt;)]
    end
    API[FastAPI /v1]
    DASH[Streamlit dashboard]
    GEE --> ING
    OM --> ING
    GAUGE --> ING
    ING --> RAW --> PROV
    RAW --> FEAT --> PROC
    PROC --> TRAIN --> ART
    TRAIN --> REP
    PROC --> DRIFT
    ART --> DRIFT --> REP
    DRIFT -. recommends tier .-> RETRAIN --> ART
    GEE --> LAKES --> REP
    PROC --> QB --> REP
    ART --> API
    PROC --> API
    REP --> API
    ART --> DASH
    REP --> DASH
```

## Forecast data flow and leakage controls

```mermaid
flowchart TD
    A[Raw daily tables] -->|schema + range + completeness checks| B[Merged daily frame]
    B -->|shift each source by its availability lag<br/>Q 1 d, MODIS 1 d, ERA5 5 d| C[Information available at issue date t]
    C -->|backward rolling windows, causal snow gap-fill| D[Features at t]
    B -->|Q at t+h| E[Targets y_h1, y_h7, y_h30]
    D --> F{Split by issue date<br/>embargo: t+h stays in period}
    E --> F
    F -->|2015-2020| G[train: fit + rolling-origin CV]
    F -->|2021-2022| H[calibration: CQR offsets]
    F -->|2023-2025| I[test: scored once, logged]
    G --> J[selected config, 3 seeds]
    J --> H --> K[calibrated P10/P50/P90]
    K --> I
    I --> L[registry candidate + gate]
    L -->|named approver| M[production]
```

## Governance flow

```mermaid
flowchart LR
    W[weekly drift check] --> Q{alerts?}
    Q -->|data_quality / pipeline| T1[Tier 1: fix inputs]
    Q -->|residual, coverage only| T2[Tier 2: recalibrate CQR]
    Q -->|residual, QS ratio > 2, persistent| T3[Tier 3: retrain candidate]
    Q -->|season-aware covariate only| T0[monitor]
    T2 --> C[candidate + same-window incumbent rescoring]
    T3 --> C
    C --> G{gate: floors, coverage band,<br/>beats climatology, >= 2% better}
    G -->|fail| R[stays candidate, logged]
    G -->|pass| AP{named approver}
    AP --> P[production]
    P -->|problem| RB[rollback to previous]
```

## Repository layout

| path | purpose |
|---|---|
| `configs/` | forecast protocol, drift, governance, lakes, quantum settings |
| `src/ingest/` | Earth Engine, GloFAS ingest; EE auth; provenance manifest |
| `src/validate/` | pandera schemas, range and completeness checks |
| `src/data/` | SYNTHETIC fixture generator (demo/tests only) |
| `src/features/` | leakage-safe feature table, dataset versioning |
| `src/models/` | baselines, LightGBM quantile, quantile LSTM, CQR |
| `src/evaluate/` | splits, metrics, block bootstrap |
| `src/registry/` | model registry, gate, promotion, rollback, audit log |
| `src/pipeline/` | train, retrain, refresh jobs |
| `src/drift/` | monitors, tier policy, replay and synthetic evaluation |
| `src/quantum/` | VQC and matched classical models, benchmark |
| `src/lakes/` | lake segmentation core (NumPy) and Earth Engine pipeline |
| `src/serving/` | read model for API and dashboard |
| `api/` | FastAPI app and schemas |
| `dashboard/` | Streamlit multipage app |
| `docker/` | Dockerfile, entrypoint, compose |
| `infra/` | Azure Bicep |
| `.github/workflows/` | CI and CD |
| `tests/` | offline tests on SYNTHETIC fixtures |
| `reports/real/` | committed result tables from real-data runs |
