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

## Results (run 2026-10-20, rule frozen 08:20:45Z before the test was sampled)

Full tables: `reports/real/lake_variants.md`; frozen rule `configs/lakes_rule.yaml`. Blocks: train
66, validation 34, test 34 (domain slope < 25 deg). Validation 2020: 859 samples (400 water).

| variant | train F1 (2019) | val IoU | val F1 | val precision | val recall | val area error |
|---|---|---|---|---|---|---|
| **A (current; selected)** | 0.701 | **0.156** | 0.269 | 0.162 | 0.807 | +400% |
| B MNDWI | 0.709 | 0.044 | 0.084 | 0.044 | 0.780 | +1653% |
| C MNDWI, slope 20 | 0.610 | 0.094 | 0.172 | 0.095 | 0.883 | +826% |
| D MNDWI, SWIR guard | 0.735 | 0.029 | 0.057 | 0.030 | 0.767 | +2490% |
| E MNDWI, slope 20, SWIR guard | 0.608 | 0.093 | 0.170 | 0.094 | 0.872 | +825% |
| F = E + SAR union | (E's thresholds) | 0.093 | 0.170 | 0.094 | 0.872 | +825% |

- **No variant improved on the current rule**; A was selected by the registered rule. Its tuned
  thresholds (NDWI > 0.2, NIR < 0.3, VV < -20 dB, slope < 12 deg) are identical to the v1 rule.
- **Test 2021 (once):** A, IoU 0.077, F1 0.144, precision 0.090, recall 0.362, area +303%
  (1,140 samples, 542 water; 0.097 km2 JRC water). Lower than the v1 test IoU 0.11 mainly because
  the wider domain now counts JRC water on 12-25 deg slopes as missed. Not an untouched benchmark
  (see Disclosure).
- MNDWI variants matched or beat A on the 2019 train blocks but collapsed on 2020, and several
  tuned thresholds sit at the grid edge (t_idx = -0.1): the SWIR-based index does not transfer
  between years here (descriptive; not tested further, since the variant list is closed).
- Within the MNDWI variants, the 20 deg slope limit improved both validation recall and precision
  (C vs B: recall 0.88 vs 0.78, precision 0.095 vs 0.044; E vs D similarly), but not enough to
  reach A, which uses NDWI with the 12 deg limit. An NDWI + 20 deg variant was not in the
  registered list and was not tried.

## Deviations

- 2026-10-20: step 4 (rerun annual areas, objects and Hi-MAG with the frozen rule) was **not run**.
  The frozen rule equals the v1 rule (same index, thresholds, slope limit and fusion; the v1 zone
  and the v2 rule mask select the same pixels), so the outputs would reproduce
  `reports/real/lake_analysis.md` and `himag_comparison.md`. The `--frozen-rule` and
  `inventory --version v2` code paths remain for a future rule.
