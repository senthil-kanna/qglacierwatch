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
Objects growing >= 5%/yr with Benjamini-Hochberg q < 0.05 (across all objects) receive a **screening flag** to prioritise inspection. A flag
is not evidence of glacial-lake outburst-flood danger, which depends on dam type, moraine stability,
trigger processes and downstream exposure.

## Results (run 2026-10-19, 20 m; full tables in `reports/real/lake_analysis.md`)

Split: water-stratified blocks (see `docs/protocol.md` deviations). Blocks are ranked by 2019 JRC
water area; wet blocks in groups of 4 get train/train/val/test, dry blocks are split 50/25/25 at
random. Wet blocks per split: train 6, val 4, test 3.

- Lake zone: 240 km2. Thresholds tuned on 63 train blocks, 2019: NDWI > 0.2, NIR < 0.3 (train F1 0.80); VV < -20 dB (train F1 0.23, SAR alone is weak in this terrain).
- Validation (32 blocks, 2020; 0.076 km2 of JRC water, 352 water samples): optical IoU 0.37, F1 0.54, precision 0.38, recall 0.94, area +148%. Fusion equals optical (optical composite valid on >= 99.7% of the zone); SAR-only IoU 0.04.
- **Test (32 blocks, 2021; 0.087 km2 of JRC water, 475 water samples) is now interpretable, and skill is low:** optical/fusion IoU 0.11, F1 0.20, precision 0.13, recall 0.39, area +197%. SAR-only IoU 0.16 (precision 1.0, recall 0.16, area -84%). The detector over-maps water (likely shadow, wet snow and turbid shallows that JRC does not label) and generalises poorly from 2019 thresholds to 2021. Caveat: 2021 imagery was scored once before under the old split, so this score is not fully blind.
- Annual zone water area (all 7 years comparable): 0.64-1.15 km2, no trend (Theil-Sen -0.005 km2/yr, 95% CI -0.16..+0.17, Kendall p = 1.0). Given the test precision, absolute areas are likely overestimated; year-to-year swings of ~40% include segmentation noise.
- 34 lake objects >= 0.01 km2 (largest ~0.08 km2). **No object is flagged** after Benjamini-Hochberg correction (smallest q = 0.09). Under the earlier uncorrected rule one object (+9.7%/yr, p = 0.03, q = 0.34) was flagged; that flag was a likely chance result.

## Inventory comparison

Hi-MAG and ICIMOD inventories were not ingested (not on Earth Engine; licence and coverage not
verified here). `src.lakes.pipeline.compare_inventory(inventory.geojson, lake_objects.geojson)`
reports overlap counts and areas once an inventory file is obtained. No equivalence is claimed.
