# Gauge check: GloFAS and forecasts vs observed discharge at Bajoura Bridge (registered)

Registered 2026-10-20 before the registered comparison was run. Later commits may implement this
file but not change it; deviations are logged at the end. No model is retrained or tuned on these
observations.

## Source and provenance (verified 2026-10-20)

| file (kept in git-ignored `data/external/nwdp_hp_discharge/`) | dataset | SHA-256 |
|---|---|---|
| `river_discharge_tele_hr_himachal_pradesh_hp_1970_2025.csv` | River Discharge (Telemetry - Hourly), Himachal Pradesh Water Department, NWDP dataset `624d25a8-fb46-4647-951c-07ee1aaaeda1`, code WQT00022, v1 | a090653339678a2be51cf9c3be747094ce9e07a8dcd86b9aca1b5f5e485b0583 |
| `river_discharge_tele_hr_himachal_pradesh_hp_2026_2030.csv` | same dataset, resource `4d8b0b68-...`; downloaded by Claude 2026-10-20 | 486a153f86737e2f39a4f07b04690235b518f52620e4b22eaff08ce62e0a425f |
| `river_discharge_manual_daily_himachal_pradesh_hp_2001_2025.csv` | River Discharge (Manual - Daily), NWDP dataset `d3730442-...`, code WQT00023, v1 (not used: no main-stem Beas station near the outlet) | e316648b98f253659ee36d28aa2344ed4a288d6e2f251e662198438a1ca4a375 |

- Portal: National Water Data Portal (https://nwdp.nwic.gov.in), National Water Informatics Centre
  (NWIC), Ministry of Jal Shakti. Download URLs recorded in the files' Zone.Identifier
  (`https://nwdp.nwic.gov.in/dataset/<id>/resource/<id>/download/<file>.csv`). Not India-WRIS.
- Data producer: Himachal Pradesh Water Department (state agency), not CWC.
- Terms: dataset licence field "Other (Open)" without a URL; access control "Public"; quality,
  validation and error-handling metadata are blank. NWDP Copyright Policy: reproduction free of
  charge with accurate reproduction and prominent source acknowledgement, except material explicitly
  identified as third-party copyright. National Water Data Policy 4.4.1-4.4.2: unclassified data
  hosted by NWIC are free to download; use must be acknowledged naming the data producer.
- **Decision:** results derived from the data are published with acknowledgement ("Data: Himachal
  Pradesh Water Department, via National Water Data Portal, NWIC"). **Raw and cleaned series are not
  committed or redistributed** until redistribution terms are confirmed with NWIC
  (helpdesk-nwic@gov.in). Only aggregate metrics go into the repository.

## Station

Bajoura Bridge, telemetry, 31.85000 N, 77.16972 E (Mandi district), 3.7 km from the catchment
outlet used here (31.877 N, 77.146 E) and on the Beas main stem below the Parvati confluence
(location only; the river, basin, tehsil and method fields in the file are blank). Its catchment is
somewhat larger than ours; catchment area, rating curve, sensor type and maintenance history are
**unknown**. Because the station's measurement method and data quality cannot be established from
the source, this is reported as a **consistency check against a state telemetry gauge**, not as
independent validation.

## Prior exposure (disclosure)

Before registration, a quick exploratory comparison of daily means (>= 48 readings, local calendar
days) with GloFAS for 2023-07-14..2025-12-26 was printed in conversation: 522 days, correlation
0.53, NSE 0.21, median GloFAS/observed ratio 0.23-0.32 in May-June and 1.7-2.4 in Sep-Nov. No model
was fitted on it. The 2026 observations were only counted (217 days with >= 48 readings), not
compared with anything.

## Cleaning (raw files never modified; script `src/evaluate/gauge_check.py`)

1. Select `Station == "Bajoura Bridge"`; parse `Data Acquisition Time` as `%d-%m-%Y %H:%M`, assumed
   **IST (UTC+5:30)** and converted to UTC so daily means align with GloFAS/ERA5 UTC days.
2. Non-numeric values and negatives -> missing. Duplicate timestamps: keep the first (counted).
3. Daily mean (UTC day) only with **>= 48 valid readings** (12 h at the nominal 15-min interval);
   otherwise the day is missing. Gaps are never filled or interpolated.
4. Flags (kept, never removed in the primary analysis):
   - `zero`: any reading of exactly 0 in the day;
   - `spike`: a reading > 3x the median of readings within +/-2 h and > 50 m3/s above it;
   - `flatline`: >= 24 identical consecutive readings (6 h);
   - `extreme`: daily mean above the 99.5th percentile of all valid daily means, listed by date for
     manual review against known events (treated as possibly genuine).
   Primary analysis: all valid days. Sensitivity analysis: excluding days with any flag.
5. Outputs: aggregate counts (readings, valid days, missing days per month, flags) only.

## Comparisons (run once)

Seasons by target month: winter DJF, pre-monsoon MAM, monsoon JJAS, post-monsoon ON
(`configs/forecast.yaml`). Seasonal metrics are reported only with n >= 30 days, otherwise
"insufficient".

- **C1 GloFAS vs observed.** Stored target series (`data/fresh2026/raw/discharge.parquet`,
  Open-Meteo `seamless_v4`; forecast-derived on all overlap days) vs observed daily means, period
  2023-07-14..2026-09-30 (all valid days). Metrics: n, mean obs, mean GloFAS, bias ratio
  (mean GloFAS / mean obs), median daily ratio, Pearson r, NSE, KGE, MAE; overall and by season,
  and separately for 2023-2025 and 2026.
- **C2a Original forecasts.** `artifacts/real/hindcasts.parquet`, split `test` (target dates
  2023-2025; trained on GloFAS 2015-2020, per-season CQR on 2021-2022), all 4 models, h = 1/7/30,
  target dates with a valid observation.
- **C2b Fresh 2026 forecasts.** `artifacts/fresh2026/real/hindcasts.parquet`, split `test`
  (target dates Jan-Sep 2026), same models and horizons.
  For C2a/C2b: P50 NSE, KGE, MAE, RMSE; QS (P10/P50/P90 pinball, same definition as the main
  evaluation); P10-P90 coverage and mean width; each also against GloFAS on the **same dates** for
  reference; by season where n >= 30. Calibration and training splits are not scored (they were
  used to fit models or offsets).

Results: `reports/real/gauge_check.{json,md}` (aggregates only).

## Limitations stated in the report

Unknown method/rating curve/quality control; telemetry without validation flags; 3.7 km downstream
location with a larger catchment; IST assumption for timestamps; large gaps (e.g. Dec 2024 -
Apr 2025 and Oct - Nov 2025); 2.5 years only, so no retraining; forecasts were trained to reproduce
GloFAS, so their errors against the gauge combine model error and GloFAS error.

## Deviations

(none yet)
