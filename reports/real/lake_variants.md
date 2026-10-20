# Lake segmentation v2: variants (generated 2026-10-20T08:20:45+00:00)

Domain: basin, > 3500 m, slope < 25 deg. Thresholds tuned on train blocks 2019; selection on validation blocks 2020; test blocks 2021 scored once after freezing. JRC labels end in 2021 and the 2021 test blocks were scored twice before (different domain/splits), so the test is not an untouched benchmark.

| variant | index | slope < | SWIR guard | SAR union | thresholds | val IoU | F1 | precision | recall | area error | n (water) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A **(selected)** | ndwi | 12 | no | no | t_idx=0.2, t_nir=0.3, t_vv=-20 | 0.156 | 0.269 | 0.162 | 0.807 | +399.5% | 859 (400) |
| B | mndwi | 12 | no | no | t_idx=0.1, t_nir=0.2, t_vv=-20 | 0.044 | 0.084 | 0.044 | 0.780 | +1653.2% | 859 (400) |
| C | mndwi | 20 | no | no | t_idx=-0.1, t_nir=0.08, t_vv=-20 | 0.094 | 0.172 | 0.095 | 0.883 | +825.8% | 859 (400) |
| D | mndwi | 12 | yes | no | t_idx=-0.1, t_nir=0.3, t_vv=-20, t_swir=0.05 | 0.029 | 0.057 | 0.030 | 0.767 | +2489.5% | 859 (400) |
| E | mndwi | 20 | yes | no | t_idx=-0.1, t_nir=0.08, t_vv=-20, t_swir=0.08 | 0.093 | 0.170 | 0.094 | 0.872 | +824.8% | 859 (400) |
| F | mndwi | 20 | yes | yes | t_idx=-0.1, t_nir=0.08, t_vv=-20, t_swir=0.08 | 0.093 | 0.170 | 0.094 | 0.872 | +824.8% | 859 (400) |

## Test (2021, scored once)

| variant | IoU | F1 | precision | recall | area error | n (water) | JRC water km2 |
|---|---|---|---|---|---|---|---|
| A | 0.077 | 0.144 | 0.090 | 0.362 | +303.3% | 1140 (542) | 0.0967 |
