# Glacial-lake analysis (generated 2026-10-19T18:05:15+00:00)

Labels are JRC Global Surface Water yearly classes (Landsat): a silver reference, not an authoritative glacial-lake inventory. Scores measure agreement with JRC.

Zone: basin above 3500 m, slope < 12 deg (240 km2). Window 09-15..10-31 each year.

Tuned thresholds (train blocks, 2019): NDWI > 0.2, NIR < 0.3, VV < -20.0 dB.

| split (year) | variant | IoU | Dice/F1 | precision | recall | area error | n |
|---|---|---|---|---|---|---|---|
| val (2020) | optical_only | 0.370 | 0.540 | 0.378 | 0.940 | +148.4% | 841 |
| val (2020) | sar_only | 0.038 | 0.072 | 0.047 | 0.153 | +223.3% | 842 |
| val (2020) | fusion | 0.369 | 0.539 | 0.378 | 0.937 | +147.7% | 842 |
| test (2021) | optical_only | 0.109 | 0.196 | 0.131 | 0.389 | +197.0% | 1026 |
| test (2021) | sar_only | 0.162 | 0.279 | 1.000 | 0.162 | -83.8% | 1027 |
| test (2021) | fusion | 0.109 | 0.196 | 0.131 | 0.389 | +197.0% | 1027 |

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

Rapid-growth flag = SCREENING indicator for prioritising inspection, not evidence of GLOF hazard. Flags use Benjamini-Hochberg q < 0.05 across all 34 objects (false discovery rate control).

| object | mean area km2 | Theil-Sen km2/yr | rel./yr | Kendall p | BH q | n years | screening flag |
|---|---|---|---|---|---|---|---|
| 15 | 0.0790 | -0.0008 | -1.0% | 0.773 | 1.000 | 7 |  |
| 22 | 0.0739 | +0.0000 | +0.0% | 1.000 | 1.000 | 7 |  |
| 0 | 0.0457 | +0.0000 | +0.0% | 1.000 | 1.000 | 7 |  |
| 16 | 0.0397 | +0.0002 | +0.6% | 0.224 | 1.000 | 7 |  |
| 6 | 0.0319 | +0.0009 | +6.9% | 1.000 | 1.000 | 7 |  |
| 30 | 0.0291 | +0.0021 | +9.7% | 0.030 | 0.342 | 7 |  |
| 29 | 0.0218 | -0.0073 | -17.6% | 0.003 | 0.094 | 7 |  |
| 10 | 0.0177 | +0.0017 | +9.4% | 0.362 | 1.000 | 7 |  |
| 24 | 0.0176 | -0.0002 | -1.3% | 0.773 | 1.000 | 7 |  |
| 1 | 0.0173 | -0.0006 | -3.2% | 0.562 | 1.000 | 7 |  |
| 25 | 0.0138 | +0.0007 | +8.2% | 1.000 | 1.000 | 7 |  |
| 31 | 0.0126 | -0.0008 | -6.0% | 0.011 | 0.182 | 7 |  |
| 7 | 0.0119 | -0.0000 | -0.0% | 0.878 | 1.000 | 7 |  |
| 21 | 0.0114 | +0.0003 | +3.4% | 0.381 | 1.000 | 7 |  |
| 9 | 0.0104 | +0.0002 | +3.1% | 0.761 | 1.000 | 7 |  |
