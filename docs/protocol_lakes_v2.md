# Lake segmentation improvement: registered protocol (v2)

Registered 2026-10-20, before any variant below was computed or scored. Later commits may implement
this file but not change it; deviations are logged at the end.

## Motivation (from existing results)

- vs JRC (test 2021): precision 0.13, recall 0.39, area +197%: false water outside lakes.
- vs Hi-MAG 2017: 17/21 lakes found, but matched lake areas ~0.5x Hi-MAG: lake extent too small.
- The current evaluation zone (slope < 12 deg) removes pixels before scoring, so a slope filter
  that cuts lake margins cannot be detected by the JRC scores.

## Disclosure

JRC GSW 1.4 labels end in 2021, so validation (2020) and test (2021) use the same years as before,
and the 2021 test blocks were scored twice already (random split; stratified split). The test score
below is therefore **not a new, untouched benchmark**; only the selection on validation is clean.

## Evaluation domain and data

- Domain D = basin, elevation > 3,500 m, slope < 25 deg (Copernicus GLO-30). Wider than the old
  12 deg zone so slope filters are part of the predictor and pixels they remove count as
  "predicted not water".
- Same years (tune 2019, validation 2020, test 2021), window, composites, labels (JRC with 1-pixel
  edge buffer), 5 km blocks, stratified block split rule (2019 water, groups of 4, seed 42),
  20 m scale, and stratified pixel sampling (2,000 per class per year, seeds as before) inside D.
- Additional sampled bands: MNDWI = (B3 - B11)/(B3 + B11), B11 (SWIR, 20 m), slope (deg).

## Variants (complete list; nothing else is tried)

| id | optical index | slope limit | SWIR guard B11 < t_swir | SAR |
|---|---|---|---|---|
| A (current) | NDWI (B3, B8) > t_idx and B8 < t_nir | 12 deg | no | VV < t_vv where optical invalid |
| B | MNDWI (B3, B11) > t_idx and B8 < t_nir | 12 | no | as A |
| C | MNDWI | 20 | no | as A |
| D | MNDWI | 12 | yes | as A |
| E | MNDWI | 20 | yes | as A |
| F | as E | 20 | yes | as A, plus water where VV < t_vv and MNDWI > 0 on optically valid pixels |

Grids: t_idx in {-0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6}; t_nir in {0.08, 0.12, 0.16, 0.20, 0.30};
t_swir in {0.03, 0.05, 0.08, 0.12}; t_vv in {-22, -20, -18, -16, -14} dB.

## Fitting, selection, test

1. Thresholds per variant: weighted F1 on train blocks, 2019 only (pixels outside the variant's
   slope limit predicted not water). t_vv tuned once on train SAR samples; F reuses E's optical
   thresholds and t_vv (no extra tuning).
2. Selection: highest validation IoU (val blocks, 2020, fused prediction). Within 0.01 IoU of the
   best, the simpler variant wins (order A < B < C = D < E < F; C before D on ties).
3. Freeze the selected variant and thresholds (`configs/lakes_rule.yaml`), then score the test
   blocks (2021) **once** for A and for the selected variant. All validation scores for all variants
   are reported.
4. Secondary, after freezing: rerun annual areas and lake objects 2019-2025 with the frozen rule,
   then rerun the Hi-MAG comparison (`src.lakes.inventory`, method unchanged). Report old vs new.

Metrics: IoU (primary), Dice/F1, precision, recall, area error, sample counts, as before.

## Deviations

(none yet)
