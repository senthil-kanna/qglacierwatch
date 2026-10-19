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

## Results (run 2026-10-19, 20 m; full tables in `reports/real/lake_analysis.md`)

- Lake zone: 240 km2. Thresholds tuned on 64 train blocks, 2019: NDWI > 0.2, NIR < 0.3 (train F1 0.87); VV < -20 dB (train F1 0.28, SAR alone is weak in this terrain).
- Validation (32 blocks, 2020; 0.18 km2 of JRC water): optical IoU 0.31, F1 0.48, precision 0.43, recall 0.53, area +21%. Fusion is the same as optical because the optical composite was valid on >= 99.7% of the zone; SAR-only IoU 0.06.
- **Test (31 blocks, 2021) is not interpretable.** The random block split placed almost no lakes in the test blocks: 0.00076 km2 of JRC water and 27 water samples. The reported test IoU 0.002 and area error +29,996% mean "almost no true water to find", not a measured skill level. This is a split-design flaw: lakes are rare (34 objects in 240 km2) and the split was not stratified by water presence.
- Annual zone water area (all 7 years comparable): 0.64-1.15 km2, no trend (Theil-Sen -0.005 km2/yr, 95% CI -0.16..+0.17, Kendall p = 1.0). Year-to-year swings of ~40% are larger than any trend and include segmentation noise.
- 34 lake objects >= 0.01 km2 (largest ~0.08 km2). One object gets the screening flag (+9.7%/yr, p = 0.03). Testing 34 objects at p < 0.05 would give ~1.7 false flags by chance alone, so this single flag is **not evidence of growth**; it only marks a lake to look at in imagery.

### Required protocol change before re-scoring (not yet run)

Assign blocks to splits stratified by JRC water presence (so each split contains lakes), pick the
stratification and a new held-out year *before* looking at scores, log it as a deviation in
`docs/protocol.md`, and apply a multiple-testing correction (Benjamini-Hochberg) to growth flags.

## Inventory comparison

Hi-MAG and ICIMOD inventories were not ingested (not on Earth Engine; licence and coverage not
verified here). `src.lakes.pipeline.compare_inventory(inventory.geojson, lake_objects.geojson)`
reports overlap counts and areas once an inventory file is obtained. No equivalence is claimed.
