import json

import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data
from src import config

res = data.report("lake_analysis")
if not res:
    st.info("Lake analysis not generated in this mode. Run `python -m src.lakes.pipeline` (Earth Engine, real mode).")
    st.stop()

st.info(
    "Labels are JRC Global Surface Water yearly classes (Landsat), a silver reference rather than a glacial-lake inventory. "
    "Rapid-growth flags are a screening aid for prioritising inspection, not evidence of outburst-flood hazard.",
    icon=":material/info:",
)
p = res["params"]
st.caption(
    f"Lake zone: basin above {res['config']['min_elevation_m']} m, slope < {res['config']['max_slope_deg']} deg ({res['zone_km2']:.0f} km2) | "
    f"window {res['config']['window'][0]}..{res['config']['window'][1]} | {res['config']['scale_m']} m | "
    f"NDWI > {p['t_ndwi']}, NIR < {p['t_nir']}, VV < {p['t_vv']} dB | generated {res['generated_utc']}"
)

rows = []
for split in ("val", "test"):
    for v in ("optical_only", "sar_only", "fusion"):
        m = res["evaluation"][split][v]
        rows.append({"split": f"{split} ({res['splits'][split + '_year']})", "variant": v, **{k: m[k] for k in ("iou", "dice_f1", "precision", "recall", "area_error_frac", "n")}})
with st.container(border=True):
    st.subheader("Segmentation agreement with JRC (held-out spatial blocks and years)")
    st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={c: st.column_config.NumberColumn(format="%.3f") for c in ("iou", "dice_f1", "precision", "recall", "area_error_frac")})

annual = pd.DataFrame(res["annual"])
with st.container(border=True):
    st.subheader("Annual water area in the lake zone")
    long = annual.melt(["year", "comparable"], ["optical_km2", "fusion_km2", "sar_km2"], var_name="variant", value_name="km2")
    chart = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("year:O"), y=alt.Y("km2:Q", title="Water area (km2)"), color="variant:N",
        shape=alt.Shape("comparable:N", title="Comparable year"), tooltip=["year", "variant", "km2", "comparable"],
    )
    st.altair_chart(chart.properties(height=280), width="stretch")
    st.caption("Only comparable years (optical composite observed >= 90% of the zone) enter trends.")
    st.dataframe(annual[["year", "window", "optical_km2", "fusion_km2", "sar_km2", "valid_frac", "comparable", "s2_scenes", "s1_scenes"]], hide_index=True)

obj = res["objects"]
art = config.artifact_dir("real") / "lakes"
with st.container(border=True):
    st.subheader(f"Lake objects ({obj['count']}, {obj.get('flagged', 0)} screening flags)")
    if obj["top"]:
        top = pd.DataFrame([{"id": o["id"], "mean area km2": o["mean_area_km2"], "Theil-Sen km2/yr": o["growth"]["slope_km2_per_yr"], "rel. change/yr": o["growth"]["rel_change_per_yr"], "Kendall p": o["growth"]["kendall_p"], "years": o["growth"]["n_years"], "flag": o["flag"]} for o in obj["top"]])
        st.dataframe(top, hide_index=True)
    overlays = sorted(art.glob("overlay_*.png"))
    if overlays:
        cols = st.columns(len(overlays))
        for c, path in zip(cols, overlays, strict=True):
            c.image(str(path), caption=f"Static S2 median composite {path.stem.split('_')[1]} post-monsoon, water mask in cyan (largest object area). Not a live image.")
    gj = art / "lake_objects.geojson"
    if gj.exists():
        with st.expander("Lake object polygons (GeoJSON)"):
            st.caption(f"{len(json.loads(gj.read_text())['features'])} polygons in {gj}")
st.caption(res["inventory_comparison"])
