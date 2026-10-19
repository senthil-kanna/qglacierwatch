"""Upstream catchment of the gauge, traced through HydroBASINS NEXT_DOWN links."""

from collections import defaultdict, deque

import ee


def upstream_basin_ids(lon: float, lat: float, level: int, search_deg: float = 2.0) -> list[int]:
    """Return HYBAS_IDs of the sub-basin containing the gauge plus everything upstream of it."""
    basins = ee.FeatureCollection(f"WWF/HydroSHEDS/v1/Basins/hybas_{level}")
    outlet = basins.filterBounds(ee.Geometry.Point(lon, lat)).first()
    outlet_id = int(outlet.get("HYBAS_ID").getInfo())

    # Pull only the link attributes (no geometry) for the surrounding region.
    window = ee.Geometry.Rectangle([lon - search_deg, lat - search_deg, lon + search_deg, lat + search_deg])
    links = basins.filterBounds(window).select(["HYBAS_ID", "NEXT_DOWN"], None, False).getInfo()["features"]

    upstream_of = defaultdict(list)
    for f in links:
        p = f["properties"]
        upstream_of[int(p["NEXT_DOWN"])].append(int(p["HYBAS_ID"]))

    ids, queue = [], deque([outlet_id])
    while queue:
        current = queue.popleft()
        ids.append(current)
        queue.extend(upstream_of.get(current, []))
    return ids


def basin_geometry(lon: float, lat: float, level: int) -> ee.Geometry:
    ids = upstream_basin_ids(lon, lat, level)
    basins = ee.FeatureCollection(f"WWF/HydroSHEDS/v1/Basins/hybas_{level}")
    return basins.filter(ee.Filter.inList("HYBAS_ID", ids)).union(maxError=100).geometry()
