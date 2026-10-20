# Data card: Beas-above-Bhuntar daily dataset

| field | value |
|---|---|
| dataset id | `2b46646ce1c0` (content hash of feature table + lag/horizon/warm-up config) |
| rows | 3,943 issue dates, 2015-03-17 .. 2025-12-31 (75-day warm-up dropped) |
| raw files | `data/raw/{basin.geojson, modis_snow.parquet, era5_land.parquet, discharge.parquet}`; SHA-256 in `data/raw/MANIFEST.json` |
| processed | `data/processed/real/features_<id>.parquet` + `.json` metadata (validation report included) |
| target | `y_h{1,7,30}` = GloFAS v4 discharge on t+h, m3/s (modelled: GloFAS v4 reanalysis to 2023-08-04, forecast-derived from 2023-08-05) |
| provenance | `src/ingest/provenance.py` (licences and product IDs per file); see `docs/data_access.md` |
| regenerate | `python -m src.ingest.earth_engine && python -m src.ingest.discharge && python -m src.features.build` |

## Collection

Basin means over the HydroBASINS level-8 catchment traced upstream of the outlet (3,532 km2):
MODIS MOD10A1 NDSI snow cover (snow = NDSI >= 10, cloud-free share = valid pixels / all pixels,
`snow_frac_valid` only when >= 20% of the basin is visible), ERA5-Land daily aggregates (unit
conversions K to degC, m to mm), GloFAS v4 discharge at one grid cell via Open-Meteo.

## Quality

| table | days present / expected | longest gap | NaNs |
|---|---|---|---|
| MODIS | 3,997 / 4,018 | 12 d | `snow_frac_valid` 1,190; `ndsi_mean` 347 |
| ERA5-Land | 4,018 / 4,018 | 0 | 0 |
| GloFAS | 4,018 / 4,018 | 0 | 0 |

Schema/range checks (pandera) pass. Monthly mean discharge: 41.8 (Jan) .. 245.1 (Aug) m3/s.

## Limitations

GloFAS is not an observation and seems to miss the pre-monsoon snowmelt rise. ERA5-Land SWE is
contaminated by glacier cells. MODIS is cloud-limited in the monsoon. Basin means hide elevation
gradients. The SYNTHETIC fixture (`data/synthetic/`) shares the schema but is not data about the Beas.
