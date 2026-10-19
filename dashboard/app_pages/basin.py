import altair as alt
import pydeck as pdk
import streamlit as st

from dashboard import data
from src import config

data.provenance_banner()
gj = data.basin_geojson()

col1, col2 = st.columns([3, 2])
with col1, st.container(border=True):
    st.subheader("Catchment above Bhuntar")
    if gj:
        layer = pdk.Layer("GeoJsonLayer", {"type": "Feature", "geometry": gj}, stroked=True, filled=True, get_fill_color=[30, 120, 200, 50], get_line_color=[30, 80, 160], line_width_min_pixels=2)
        pts = pdk.Layer(
            "ScatterplotLayer",
            [{"name": "Outlet (approx. Bhuntar)", "lon": config.GAUGE_LON, "lat": config.GAUGE_LAT}, {"name": "GloFAS cell", "lon": config.GLOFAS_LON, "lat": config.GLOFAS_LAT}],
            get_position=["lon", "lat"],
            get_radius=1500,
            get_fill_color=[220, 50, 50],
            pickable=True,
        )
        st.pydeck_chart(pdk.Deck(layers=[layer, pts], initial_view_state=pdk.ViewState(latitude=32.1, longitude=77.25, zoom=8), tooltip={"text": "{name}"}, map_style=None))
        st.caption("Static polygon traced from HydroBASINS level 8 (3,532 km2). Not a live layer.")
    else:
        st.info("Basin polygon available in real mode only (data/raw/basin.geojson).")
with col2, st.container(border=True):
    st.subheader("Data sources")
    st.markdown(
        "- **Snow cover**: MODIS MOD10A1 v6.1, NDSI >= 10, basin mean of cloud-free pixels\n"
        "- **Meteorology**: ERA5-Land daily aggregates, basin mean\n"
        "- **Discharge**: GloFAS v4 reanalysis (modelled) at 31.825 N, 77.125 E\n"
        "- **Availability lags assumed**: discharge 1 d, MODIS 1 d, ERA5-Land 5 d"
    )

daily = data.raw_daily().reset_index()
years = sorted(daily["date"].dt.year.unique())
year = st.select_slider("Year", options=years, value=years[-1])
d = daily[daily["date"].dt.year == year]

with st.container(border=True):
    st.subheader("Snow-covered fraction (cloud-free part of basin)")
    base = alt.Chart(d).encode(x=alt.X("date:T", title=None))
    snow = base.mark_circle(size=14).encode(y=alt.Y("snow_frac_valid:Q", title="Snow fraction", scale=alt.Scale(domain=[0, 1])), opacity=alt.Opacity("valid_frac:Q", legend=alt.Legend(title="Cloud-free share")))
    st.altair_chart(snow.properties(height=220), width="stretch")
    st.caption(f"Days with < 20% cloud-free view are blank ({int(d['snow_frac_valid'].isna().sum())} of {len(d)} days in {year}).")

col1, col2 = st.columns(2)
with col1, st.container(border=True):
    st.subheader("Temperature (C)")
    st.altair_chart(alt.Chart(d).mark_line().encode(x=alt.X("date:T", title=None), y=alt.Y("temperature_2m:Q", title="Basin mean 2 m temperature")).properties(height=220), width="stretch")
with col2, st.container(border=True):
    st.subheader("Precipitation and snowmelt (mm/day)")
    long = d.melt("date", ["total_precipitation_sum", "snowmelt_sum"], var_name="variable")
    st.altair_chart(alt.Chart(long).mark_line().encode(x=alt.X("date:T", title=None), y=alt.Y("value:Q", title="mm/day"), color="variable:N").properties(height=220), width="stretch")

with st.container(border=True):
    st.subheader("Discharge (m3/s)")
    st.altair_chart(alt.Chart(d).mark_line().encode(x=alt.X("date:T", title=None), y=alt.Y("discharge_m3s:Q", title="m3/s")).properties(height=220), width="stretch")
