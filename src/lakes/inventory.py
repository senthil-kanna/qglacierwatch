"""Compare our lake objects with the Hi-MAG glacial-lake inventory (Chen et al., 2021).

Method fixed in docs/lakes.md before any score was computed:
  - reference: Hi-MAG polygons intersecting the basin, 2017 (primary) and the union of 2008-2017
  - ours: lake_objects.geojson (water in >= 2 comparable years 2019-2025, >= 0.01 km2)
  - equal-area CRS (Hi-MAG's Albers); recall on Hi-MAG lakes >= MIN_AREA_KM2
  - match = polygons intersect; overlapping lakes are grouped (connected components) so a lake
    split into two objects on one side is not double counted in area comparisons

Hi-MAG ends in 2017 and our objects start in 2019: there is no common year.

Usage:
    python -m src.lakes.inventory            # needs data/external/himag_v3 (see docs/lakes.md)
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from shapely.geometry import shape

from src import config

MIN_AREA_KM2 = 0.01
HIMAG_DIR = config.ROOT / "data" / "external" / "himag_v3" / "shp" / "Hi-MAG database"
SOURCE = {
    "citation": "Chen et al. (2021), ESSD 13, 741-766, doi:10.5194/essd-13-741-2021",
    "data": "Zenodo record 4275164, version 3.0 (2020-12-04), doi:10.5281/zenodo.4275164",
    "licence": "CC BY 4.0",
    "zip_md5": "abd64cb0a4a3584954e6ba1c04465c94",
    "years": "2008-2017 (annual, Landsat 30 m)",
}


def load_himag(shp_dir: Path, year: int, basin_wgs84) -> gpd.GeoDataFrame:
    path = shp_dir / f"Hi_MAG_database_{year}.shp"
    crs = gpd.read_file(path, rows=1).crs
    basin = gpd.GeoSeries([basin_wgs84], crs=4326).to_crs(crs).iloc[0]
    g = gpd.read_file(path, bbox=tuple(basin.bounds))
    return g[g.intersects(basin)].reset_index(drop=True)


def object_area(props_areas, year: str) -> float:
    areas = json.loads(props_areas) if isinstance(props_areas, str) else props_areas
    v = areas.get(year) if areas else None
    return float("nan") if v is None else float(v)


def _groups(ours: gpd.GeoDataFrame, ref: gpd.GeoDataFrame) -> list[tuple[set[int], set[int]]]:
    """Connected components of the bipartite 'polygons intersect' graph; only groups with both sides."""
    parent = {("o", i): ("o", i) for i in range(len(ours))} | {("r", j): ("r", j) for j in range(len(ref))}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in gpd.sjoin(ours, ref, predicate="intersects")["index_right"].items():
        parent[find(("o", int(i)))] = find(("r", int(j)))
    comps: dict = {}
    for node in parent:
        side, k = node
        comps.setdefault(find(node), (set(), set()))[0 if side == "o" else 1].add(k)
    return [c for c in comps.values() if c[0] and c[1]]


def compare(ours: gpd.GeoDataFrame, ref: gpd.GeoDataFrame, our_year: str = "2019", min_area_km2: float = MIN_AREA_KM2) -> dict:
    """Overlap and area agreement. Both frames must share a projected (metre) CRS."""
    ours, ref = ours.reset_index(drop=True), ref.reset_index(drop=True)
    ref_km2 = ref.geometry.area / 1e6
    big = ref[ref_km2 >= min_area_km2].reset_index(drop=True)
    hit_ref = big.intersects(ours.geometry.union_all()) if len(ours) else np.zeros(len(big), bool)
    hit_ours = ours.intersects(ref.geometry.union_all()) if len(ref) else np.zeros(len(ours), bool)
    u_o, u_r = ours.geometry.union_all(), ref.geometry.union_all()
    union = u_o.union(u_r).area
    pairs: list[dict[str, Any]] = []
    for oi, ri in _groups(ours, ref):
        a_ours = sum(object_area(ours.loc[i, "areas_km2"], our_year) for i in oi)
        a_ref = float(ref_km2.iloc[list(ri)].sum())
        pairs.append({"our_ids": sorted(int(ours.loc[i, "id"]) for i in oi), "himag_ids": sorted(str(ref.loc[j, "GL_ID"]) for j in ri),
                      "our_area_km2": a_ours, "himag_area_km2": a_ref, "ratio": a_ours / a_ref if a_ref > 0 else None})
    ratios = [p["ratio"] for p in pairs if p["ratio"] is not None and np.isfinite(p["ratio"])]
    big_km2 = big.geometry.area / 1e6
    return {
        "himag_lakes_all_sizes": len(ref), "himag_area_km2": float(ref_km2.sum()),
        f"himag_lakes_ge_{min_area_km2}": len(big), f"himag_area_ge_{min_area_km2}_km2": float(big_km2.sum()),
        "recall_count": float(np.mean(hit_ref)) if len(big) else None,
        "recall_area": float(big_km2[np.asarray(hit_ref)].sum() / big_km2.sum()) if len(big) else None,
        "himag_missed": [str(x) for x in big.loc[~np.asarray(hit_ref), "GL_ID"]],
        "our_objects": len(ours), "our_objects_matched": int(np.sum(hit_ours)),
        "our_unmatched_ids": [int(x) for x in ours.loc[~np.asarray(hit_ours), "id"]],
        "our_unmatched_area_km2": float(sum(object_area(a, our_year) for a in ours.loc[~np.asarray(hit_ours), "areas_km2"])),
        "polygon_iou_unions": float(u_o.intersection(u_r).area / union) if union > 0 else None,
        "matched_groups": len(pairs),
        "matched_area_ratio_median": float(np.median(ratios)) if ratios else None,
        "matched_area_ours_km2": float(sum(p["our_area_km2"] for p in pairs)),
        "matched_area_himag_km2": float(sum(p["himag_area_km2"] for p in pairs)),
        "pairs": pairs,
    }


def markdown(rep: dict) -> str:
    p, s = rep["primary_2017"], rep["ever_2008_2017"]
    k = f"himag_lakes_ge_{MIN_AREA_KM2}"
    L = [f"# Lake objects vs Hi-MAG inventory (generated {rep['generated_utc']})", "",
         f"Source: {SOURCE['citation']}; {SOURCE['data']}; licence {SOURCE['licence']}.", "",
         "**No common year:** Hi-MAG ends in 2017; our objects come from 2019-2025 imagery. Areas compare Hi-MAG 2017 with our 2019 composite. "
         "Hi-MAG maps glacial lakes only; our objects are any persistent water above 3,500 m, so unmatched objects are not necessarily errors.", "",
         "| reference | Hi-MAG lakes (all) | Hi-MAG lakes >= 0.01 km2 | recall (count) | recall (area) | our objects matched | polygon IoU of unions |",
         "|---|---|---|---|---|---|---|"]
    for name, r in (("Hi-MAG 2017", p), ("Hi-MAG ever mapped 2008-2017", s)):
        L.append(f"| {name} | {r['himag_lakes_all_sizes']} ({r['himag_area_km2']:.3f} km2) | {r[k]} | {r['recall_count']:.2f} | {r['recall_area']:.2f} | "
                 f"{r['our_objects_matched']} / {r['our_objects']} | {r['polygon_iou_unions']:.2f} |")
    L += ["", f"Matched lake groups (2017 reference): {p['matched_groups']}; total area ours (2019) {p['matched_area_ours_km2']:.3f} km2 vs Hi-MAG 2017 "
          f"{p['matched_area_himag_km2']:.3f} km2; median per-group ratio ours/Hi-MAG {p['matched_area_ratio_median']:.2f}.",
          f"Our objects without any Hi-MAG lake (2008-2017): {len(s['our_unmatched_ids'])} ({s['our_unmatched_area_km2']:.3f} km2 in 2019).",
          f"Hi-MAG 2017 lakes >= 0.01 km2 we miss: {len(p['himag_missed'])}.", "",
          "| our object ids | Hi-MAG ids | ours 2019 km2 | Hi-MAG 2017 km2 | ratio |", "|---|---|---|---|---|"]
    for q in sorted(p["pairs"], key=lambda q: -q["himag_area_km2"]):
        ratio = "-" if q["ratio"] is None else f"{q['ratio']:.2f}"
        L.append(f"| {', '.join(map(str, q['our_ids']))} | {', '.join(q['himag_ids'])} | {q['our_area_km2']:.4f} | {q['himag_area_km2']:.4f} | {ratio} |")
    L += ["", "| year | Hi-MAG lakes in basin | Hi-MAG area km2 |", "|---|---|---|"]
    for y, v in rep["himag_by_year"].items():
        L.append(f"| {y} | {v['lakes']} | {v['area_km2']:.3f} |")
    return "\n".join(L) + "\n"


def main() -> None:
    argparse.ArgumentParser().parse_args()
    if not HIMAG_DIR.exists():
        raise SystemExit(f"Hi-MAG shapefiles not found in {HIMAG_DIR}; see docs/lakes.md for the download.")
    basin = shape(json.loads((config.raw_dir("real") / "basin.geojson").read_text()))
    by_year = {y: load_himag(HIMAG_DIR, y, basin) for y in range(2008, 2018)}
    crs = by_year[2017].crs
    ours = gpd.read_file(config.artifact_dir("real") / "lakes" / "lake_objects.geojson").to_crs(crs)
    ever = gpd.GeoDataFrame(geometry=list(gpd.GeoSeries(np.concatenate([g.geometry.values for g in by_year.values()]), crs=crs).union_all().geoms), crs=crs)
    ever["GL_ID"] = [f"ever-{i}" for i in range(len(ever))]
    rep = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": SOURCE, "our_year": "2019", "min_area_km2": MIN_AREA_KM2,
        "himag_by_year": {str(y): {"lakes": len(g), "area_km2": float(g.geometry.area.sum() / 1e6)} for y, g in by_year.items()},
        "primary_2017": compare(ours, by_year[2017]),
        "ever_2008_2017": compare(ours, ever),
    }
    out = config.reports_dir("real")
    (out / "himag_comparison.json").write_text(json.dumps(rep, indent=2))
    (out / "himag_comparison.md").write_text(markdown(rep), encoding="utf-8")
    print(markdown(rep))


if __name__ == "__main__":
    main()
