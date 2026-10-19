# Glacial-lake analysis (generated 2026-10-19T15:40:06+00:00)

Labels are JRC Global Surface Water yearly classes (Landsat): a silver reference, not an authoritative glacial-lake inventory. Scores measure agreement with JRC.

Zone: basin above 3500 m, slope < 12 deg (240 km2). Window 09-15..10-31 each year.

Tuned thresholds (train blocks, 2019): NDWI > 0.2, NIR < 0.3, VV < -20.0 dB.

| split (year) | variant | IoU | Dice/F1 | precision | recall | area error | n |
|---|---|---|---|---|---|---|---|
| val (2020) | optical_only | 0.312 | 0.476 | 0.434 | 0.526 | +21.4% | 1304 |
| val (2020) | sar_only | 0.055 | 0.105 | 0.120 | 0.093 | -22.1% | 1307 |
| val (2020) | fusion | 0.312 | 0.475 | 0.434 | 0.525 | +21.1% | 1307 |
| test (2021) | optical_only | 0.002 | 0.004 | 0.002 | 0.667 | +29995.6% | 615 |
| test (2021) | sar_only | 0.000 | 0.000 | 0.000 | 0.000 | +29928.9% | 615 |
| test (2021) | fusion | 0.002 | 0.004 | 0.002 | 0.667 | +29995.6% | 615 |

> **WARNING: test scores are not interpretable.** The test blocks contain only 0.00076 km2 of reference water (27 water samples < 100). See docs/lakes.md.

## Annual water area in the lake zone (post-monsoon composites)

| year | optical km2 | fusion km2 | SAR km2 | optical valid share | comparable | S2 scenes | S1 scenes |
|---|---|---|---|---|---|---|---|
| 2019 | 0.729 | 0.732 | 0.869 | 0.999 | yes | 37 | 22 |
| 2020 | 1.077 | 1.092 | 0.354 | 0.997 | yes | 36 | 23 |
| 2021 | 1.152 | 1.154 | 0.424 | 0.999 | yes | 36 | 24 |
| 2022 | 0.639 | 0.653 | 2.069 | 0.998 | yes | 36 | 18 |
| 2023 | 0.821 | 0.826 | 0.492 | 0.999 | yes | 36 | 19 |
| 2024 | 1.001 | 1.003 | 0.431 | 0.999 | yes | 39 | 23 |
| 2025 | 0.809 | 0.817 | 0.428 | 0.998 | yes | 48 | 24 |

Zone-total fusion area trend over comparable years: -0.0045 km2/yr (95% CI -0.1638..+0.1749), Kendall p = 1.000, n = 7.

## Lake objects: 34 objects >= 0.01 km2

Rapid-growth flag = SCREENING indicator for prioritising inspection, not evidence of GLOF hazard. Flags are uncorrected for multiple testing: about 1.7 of 34 objects would pass p < 0.05 by chance.

| object | mean area km2 | Theil-Sen km2/yr | rel./yr | Kendall p | n years | screening flag |
|---|---|---|---|---|---|---|
| 15 | 0.0790 | -0.0008 | -1.0% | 0.773 | 7 |  |
| 22 | 0.0739 | +0.0000 | +0.0% | 1.000 | 7 |  |
| 0 | 0.0457 | +0.0000 | +0.0% | 1.000 | 7 |  |
| 16 | 0.0397 | +0.0002 | +0.6% | 0.224 | 7 |  |
| 6 | 0.0319 | +0.0009 | +6.9% | 1.000 | 7 |  |
| 30 | 0.0291 | +0.0021 | +9.7% | 0.030 | 7 | FLAG |
| 29 | 0.0218 | -0.0073 | -17.6% | 0.003 | 7 |  |
| 10 | 0.0177 | +0.0017 | +9.4% | 0.362 | 7 |  |
| 24 | 0.0176 | -0.0002 | -1.3% | 0.773 | 7 |  |
| 1 | 0.0173 | -0.0006 | -3.2% | 0.562 | 7 |  |
| 25 | 0.0138 | +0.0007 | +8.2% | 1.000 | 7 |  |
| 31 | 0.0126 | -0.0008 | -6.0% | 0.011 | 7 |  |
| 7 | 0.0119 | -0.0000 | -0.0% | 0.878 | 7 |  |
| 21 | 0.0114 | +0.0003 | +3.4% | 0.381 | 7 |  |
| 9 | 0.0104 | +0.0002 | +3.1% | 0.761 | 7 |  |
