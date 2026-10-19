# Glacial-lake segmentation and area analysis

Code: `src/lakes/core.py` (sensor-agnostic rules and metrics, unit-tested) and
`src/lakes/pipeline.py` (Earth Engine). Settings: `configs/lakes.yaml`. Results:
`reports/real/lake_analysis.md`, objects in `artifacts/real/lakes/lake_objects.geojson`.

## Data and preprocessing

| step | choice | reason |
|---|---|---|
| zone | basin above 3,500 m with slope < 12 deg (Copernicus GLO-30 2024 DEM) | glacial lakes are high and flat; steep slopes cause SAR layover/shadow and optical terrain shadow |
| window | 15 Sep - 31 Oct each year | after the monsoon, lowest seasonal snow, lakes ice-free; same window every year for comparability |
| optical | Sentinel-2 L2A (`S2_SR_HARMONIZED`), s2cloudless probability < 40, SCL cloud/shadow/saturation removed, terrain hill-shadow from the window's median sun position, median composite | per-scene hill-shadow exceeded Earth Engine interactive limits; sun angles vary by a few degrees within the window |
| SAR | Sentinel-1 GRD IW VV (dB), 3x3 focal median per scene, median composite | speckle reduction; VV is the standard open-water polarisation |
| co-registration | both resampled by Earth Engine to the analysis grid (20 m) in EPSG:4326 pixels; S1 GRD is terrain-corrected by Earth Engine's preprocessing | no additional co-registration was performed |
| scale | 20 m | 10 m processing exceeded interactive limits; 0.01 km2 objects still span >= 25 pixels |
| years | 2019-2025 | S2 L2A has only 4-10 scenes per window in 2016-2018; mixing L1C would break comparability |

## Segmentation rules (thresholds tuned, not learned end-to-end)

- Optical: NDWI = (B3 - B8)/(B3 + B8) > t_ndwi AND B8 < t_nir. Snow and ice also have high NDWI but are bright in NIR.
- SAR: VV < t_vv dB.
- Fusion: optical where the optical composite is valid, SAR elsewhere.
- Thresholds are grid-searched for weighted F1 on train blocks of the tune year only.

## Labels and their uncertainty

JRC Global Surface Water yearly history (Landsat, 30 m), classes seasonal + permanent water, with a
1-pixel boundary buffer removed. This is an independent sensor, but it is a generic water product:
it misses small or frozen lakes, may include river channels, and stops in 2021. Scores are therefore
**agreement with JRC**, not accuracy against an authoritative glacial-lake inventory.

## Leakage control

Spatial blocks of ~5 km are assigned to train/val/test (50/25/25%, fixed seed). Thresholds: train
blocks, 2019. Variant comparison: val blocks, 2020. Final scores: test blocks, 2021. No block or year
is used for both fitting and scoring.

## Metrics

Stratified pixel samples (equal water/non-water counts) are reweighted by each class's area in the
split's blocks, so IoU, Dice/F1, precision, recall and area error estimate population values.
Optical-only is scored on optically valid pixels only; SAR-only and fusion on all sampled pixels.

## Annual areas and growth screening

Annual zone-total areas are reported for every year with a flag for comparability (optical valid
share >= 0.9). Lake objects are connected areas that are water in >= 2 comparable years and >= 0.01
km2. Per-object Theil-Sen slopes and Kendall p-values are computed when >= 5 comparable years exist.
Objects growing >= 5%/yr with p < 0.05 receive a **screening flag** to prioritise inspection. A flag
is not evidence of glacial-lake outburst-flood danger, which depends on dam type, moraine stability,
trigger processes and downstream exposure.

## Inventory comparison

Hi-MAG and ICIMOD inventories were not ingested (not on Earth Engine; licence and coverage not
verified here). `src.lakes.pipeline.compare_inventory(inventory.geojson, lake_objects.geojson)`
reports overlap counts and areas once an inventory file is obtained. No equivalence is claimed.
