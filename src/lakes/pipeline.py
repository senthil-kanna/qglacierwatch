"""Glacial-lake segmentation, evaluation and annual area analysis on Google Earth Engine.

Steps
  1. Lake zone: basin above min_elevation_m with slope < max_slope_deg (Copernicus GLO-30 DEM).
  2. Post-monsoon composites per year: Sentinel-2 L2A (s2cloudless + SCL cloud/shadow masks and
     terrain hill-shadow from each scene's sun angles) and Sentinel-1 GRD IW VV (3x3 focal median).
  3. Silver labels: JRC Global Surface Water yearly history (Landsat, independent of S1/S2), with
     mixed boundary pixels removed. Not an authoritative glacial-lake inventory.
  4. Spatial blocks (~5 km) split into train/val/test; thresholds tuned on train blocks in the tune
     year, variants compared on val blocks in the val year, final scores on test blocks in the test
     year, so no block or year is used for both fitting and scoring.
  5. Annual water area for comparable years only (optical valid share >= min_valid_frac), lake
     objects, Theil-Sen growth and a rapid-growth SCREENING flag (prioritisation, not hazard).

Usage:
    python -m src.lakes.pipeline            # needs Earth Engine credentials (real mode only)
"""

import argparse
import json
import urllib.request
from datetime import UTC, datetime

import ee
import numpy as np
import pandas as pd

from src import config
from src.ingest.ee_auth import initialize
from src.lakes import core

DEM_ID = "COPERNICUS/DEM/GLO30_2024_1"


def zone_image(basin, lc):
    dem = ee.ImageCollection(DEM_ID).filterBounds(basin).select(0).mosaic().setDefaultProjection("EPSG:4326", None, 30)
    slope = ee.Terrain.slope(dem)
    zone = dem.gt(lc["min_elevation_m"]).And(slope.lt(lc["max_slope_deg"])).clip(basin)
    return dem, zone.selfMask()


def s2_composite(basin, dem, year, lc):
    start, end = f"{year}-{lc['window'][0]}", f"{year}-{lc['window'][1]}"
    sr = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(basin).filterDate(start, end)
    prob = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(basin).filterDate(start, end)
    joined = ee.ImageCollection(ee.Join.saveFirst("cloud").apply(sr, prob, ee.Filter.equals(leftField="system:index", rightField="system:index")))

    def mask(img):
        cp = ee.Image(img.get("cloud")).select("probability")
        scl = img.select("SCL")
        clear = cp.lt(lc["cloud_prob_max"]).And(scl.neq(3)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(1))
        refl = img.select(["B2", "B3", "B4", "B8", "B11"]).divide(10000)
        return refl.updateMask(clear)

    # One terrain-shadow mask per composite from the window's median sun position (sun angles vary
    # by a few degrees within the 6-week window; per-scene hill shadows exceeded EE time limits).
    az = ee.Number(sr.aggregate_array("MEAN_SOLAR_AZIMUTH_ANGLE").reduce(ee.Reducer.median()))
    zen = ee.Number(sr.aggregate_array("MEAN_SOLAR_ZENITH_ANGLE").reduce(ee.Reducer.median()))
    lit = ee.Terrain.hillShadow(dem, az, zen, 80, True)
    comp = joined.map(mask).median().updateMask(lit)
    ndwi = comp.normalizedDifference(["B3", "B8"]).rename("ndwi")
    valid = comp.select("B3").mask().rename("opt_valid")
    n_scenes = sr.size()
    return comp, ndwi, comp.select("B8").rename("nir"), valid, n_scenes


def s1_composite(basin, year, lc):
    start, end = f"{year}-{lc['window'][0]}", f"{year}-{lc['window'][1]}"
    col = (
        ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(basin).filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW")).filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .select("VV")
    )
    return col.map(lambda i: i.focalMedian(1.5, "square", "pixels")).median().rename("vv"), col.size()


def jrc_label(year, lc):
    # YearlyHistory is masked outside the 1984-2021 maximum water extent; those pixels are "not
    # water" (class 1). Explicit no-data (class 0) stays excluded. Without unmasking, non-water
    # samples would come only from lake shores and precision would be overstated.
    wc = ee.ImageCollection(lc["labels"]["source"]).filter(ee.Filter.eq("year", year)).first().select("waterClass").unmask(1)
    water = wc.remap(lc["labels"]["water_classes"], [1] * len(lc["labels"]["water_classes"]), 0)
    observed = wc.gt(0)
    r = lc["labels"]["edge_buffer_px"]
    edge = water.focalMax(r, "square", "pixels").neq(water.focalMin(r, "square", "pixels"))
    return water.updateMask(observed.And(edge.Not())).rename("label")


def block_image(lc):
    deg_lat = lc["labels"]["block_km"] / 111.0
    deg_lon = deg_lat / np.cos(np.deg2rad(32.0))
    ll = ee.Image.pixelLonLat()
    return ll.select("longitude").divide(deg_lon).floor().multiply(10000).add(ll.select("latitude").divide(deg_lat).floor()).toInt().rename("block")


def class_areas_by_block(label, zone, block, region):
    area = ee.Image.pixelArea().divide(1e6)
    stack = area.multiply(label.eq(1)).rename("w").addBands(area.multiply(label.eq(0)).rename("l")).addBands(block).updateMask(zone)
    red = ee.Reducer.sum().repeat(2).group(groupField=2, groupName="block")
    groups = stack.reduceRegion(red, region, scale=30, maxPixels=1e10, tileScale=4).get("groups").getInfo()
    return {int(g["block"]): {"water_km2": g["sum"][0], "land_km2": g["sum"][1]} for g in groups}


def sample_year(year, basin, dem, zone, lc):
    _, ndwi, nir, valid, _ = s2_composite(basin, dem, year, lc)
    vv, _ = s1_composite(basin, year, lc)
    label = jrc_label(year, lc)
    block = block_image(lc)
    img = ndwi.unmask(-9).addBands(nir.unmask(-9)).addBands(valid.unmask(0)).addBands(vv.unmask(0)).addBands(block).addBands(label).updateMask(zone)
    n = lc["labels"]["samples_per_class"]
    fc = img.stratifiedSample(numPoints=n, classBand="label", region=basin, scale=lc["scale_m"], seed=lc["labels"]["seed"] + year, classValues=[0, 1], classPoints=[n, n], tileScale=8, geometries=False)
    df = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])
    areas = class_areas_by_block(label, zone, block, basin)
    return df, areas


def evaluate(df, areas, split_of, split, params) -> dict:
    d = df[df["block"].map(split_of) == split]
    blocks = [b for b, s in split_of.items() if s == split]
    area = {1: sum(areas.get(b, {}).get("water_km2", 0) for b in blocks), 0: sum(areas.get(b, {}).get("land_km2", 0) for b in blocks)}
    lab = d["label"].to_numpy().astype(bool)
    w = core.strata_weights(lab, area)
    opt = core.optical_water(d["ndwi"].to_numpy(), d["nir"].to_numpy(), params["t_ndwi"], params["t_nir"])
    ov = d["opt_valid"].to_numpy().astype(bool)
    sar = core.sar_water(d["vv"].to_numpy(), params["t_vv"])
    has_sar = d["vv"].to_numpy() != 0
    out = {"n_samples": int(len(d)), "n_water_samples": int(lab.sum()), "label_water_km2": area[1], "blocks": len(blocks)}
    out["optical_only"] = {**core.seg_metrics(core.weighted_confusion(opt[ov], lab[ov], w[ov])), "n": int(ov.sum()), "evaluated_on": "optically valid pixels"}
    out["sar_only"] = {**core.seg_metrics(core.weighted_confusion(sar[has_sar], lab[has_sar], w[has_sar])), "n": int(has_sar.sum())}
    fused = core.fuse(opt, ov, sar)
    out["fusion"] = {**core.seg_metrics(core.weighted_confusion(fused, lab, w)), "n": int(len(d)), "optical_share": float(ov.mean())}
    return out


def annual_areas(basin, dem, zone, params, lc):
    rows, masks = [], {}
    area = ee.Image.pixelArea().divide(1e6)
    for y in lc["annual_years"]:
        _, ndwi, nir, valid, n_s2 = s2_composite(basin, dem, y, lc)
        vv, n_s1 = s1_composite(basin, y, lc)
        opt = ndwi.gt(params["t_ndwi"]).And(nir.lt(params["t_nir"])).unmask(0)
        sar = vv.lt(params["t_vv"]).unmask(0)
        v = valid.unmask(0)
        fused = opt.where(v.Not(), sar).updateMask(zone)
        masks[y] = fused
        stack = (
            area.multiply(opt.updateMask(v)).rename("optical_km2")
            .addBands(area.multiply(fused).rename("fusion_km2"))
            .addBands(area.multiply(sar).rename("sar_km2"))
            .addBands(area.multiply(v).rename("valid_km2"))
            .addBands(area.rename("zone_km2"))
            .updateMask(zone)
        )
        r = stack.reduceRegion(ee.Reducer.sum(), basin, scale=lc["scale_m"], maxPixels=1e10, tileScale=8).getInfo()
        rows.append({"year": y, **r, "valid_frac": r["valid_km2"] / r["zone_km2"], "s2_scenes": n_s2.getInfo(), "s1_scenes": n_s1.getInfo(),
                     "window": f"{y}-{lc['window'][0]}..{y}-{lc['window'][1]}"})
        print(f"  {y}: optical {r['optical_km2']:.3f} km2, fusion {r['fusion_km2']:.3f} km2, valid {rows[-1]['valid_frac']:.3f}", flush=True)
    return pd.DataFrame(rows), masks


def lake_objects(basin, zone, masks, years, lc):
    """Objects = water in >= 2 comparable years, connected, >= min_area. Area per object per year."""
    stack = ee.ImageCollection([masks[y].unmask(0) for y in years]).sum()
    persistent = stack.gte(2).updateMask(zone).selfMask()
    min_px = int(lc["objects"]["min_area_km2"] * 1e6 / lc["scale_m"] ** 2)
    sized = persistent.updateMask(persistent.connectedPixelCount(min_px + 1, True).gte(min_px))
    vec = sized.reduceToVectors(geometry=basin, scale=lc["scale_m"], geometryType="polygon", eightConnected=True, maxPixels=1e10, tileScale=8, labelProperty="v")
    area = ee.Image.pixelArea().divide(1e6)
    band_stack = ee.Image.cat([area.multiply(masks[y].unmask(0)).rename(f"a{y}") for y in years])
    reduced = band_stack.reduceRegions(collection=vec, reducer=ee.Reducer.sum(), scale=lc["scale_m"], tileScale=8)
    return reduced.getInfo()


def overlay_png(basin, dem, year, params, lc, out_path, region):
    comp, ndwi, nir, valid, _ = s2_composite(basin, dem, year, lc)
    rgb = comp.select(["B4", "B3", "B2"]).visualize(min=0, max=0.3)
    water = ndwi.gt(params["t_ndwi"]).And(nir.lt(params["t_nir"])).selfMask().visualize(palette=["00e5ff"])
    img = ee.ImageCollection([rgb, water]).mosaic()
    url = img.getThumbURL({"region": region, "dimensions": 1024, "format": "png"})
    with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 - Earth Engine signed URL
        out_path.write_bytes(r.read())


def markdown(rep):
    L = [f"# Glacial-lake analysis (generated {rep['generated_utc']})", "",
         "Labels are JRC Global Surface Water yearly classes (Landsat): a silver reference, not an authoritative glacial-lake inventory. "
         "Scores measure agreement with JRC.", "",
         f"Zone: basin above {rep['config']['min_elevation_m']} m, slope < {rep['config']['max_slope_deg']} deg ({rep['zone_km2']:.0f} km2). "
         f"Window {rep['config']['window'][0]}..{rep['config']['window'][1]} each year.", "",
         f"Tuned thresholds (train blocks, {rep['splits']['tune_year']}): NDWI > {rep['params']['t_ndwi']}, NIR < {rep['params']['t_nir']}, VV < {rep['params']['t_vv']} dB.", "",
         "| split (year) | variant | IoU | Dice/F1 | precision | recall | area error | n |", "|---|---|---|---|---|---|---|---|"]
    for split in ("val", "test"):
        e = rep["evaluation"][split]
        for v in ("optical_only", "sar_only", "fusion"):
            m = e[v]
            L.append(f"| {split} ({rep['splits'][split + '_year']}) | {v} | {m['iou']:.3f} | {m['dice_f1']:.3f} | {m['precision']:.3f} | {m['recall']:.3f} | {m['area_error_frac']:+.1%} | {m['n']} |")
    L += ["", "## Annual water area in the lake zone (post-monsoon composites)", "", "| year | optical km2 | fusion km2 | SAR km2 | optical valid share | comparable | S2 scenes | S1 scenes |", "|---|---|---|---|---|---|---|---|"]
    for r in rep["annual"]:
        L.append(f"| {r['year']} | {r['optical_km2']:.3f} | {r['fusion_km2']:.3f} | {r['sar_km2']:.3f} | {r['valid_frac']:.3f} | {'yes' if r['comparable'] else 'no'} | {r['s2_scenes']} | {r['s1_scenes']} |")
    t = rep["zone_trend_fusion"]
    if t["slope_km2_per_yr"] is not None:
        L += ["", f"Zone-total fusion area trend over comparable years: {t['slope_km2_per_yr']:+.4f} km2/yr (95% CI {t['slope_ci95'][0]:+.4f}..{t['slope_ci95'][1]:+.4f}), Kendall p = {t['kendall_p']:.3f}, n = {t['n_years']}."]
    L += ["", f"## Lake objects: {rep['objects']['count']} objects >= {rep['config']['objects']['min_area_km2']} km2", "",
          "Rapid-growth flag = SCREENING indicator for prioritising inspection, not evidence of GLOF hazard.", "",
          "| object | mean area km2 | Theil-Sen km2/yr | rel./yr | Kendall p | n years | screening flag |", "|---|---|---|---|---|---|---|"]
    for o in rep["objects"]["top"]:
        g = o["growth"]
        rel = "-" if g["rel_change_per_yr"] is None else f"{g['rel_change_per_yr']:+.1%}"
        sl = "-" if g["slope_km2_per_yr"] is None else f"{g['slope_km2_per_yr']:+.4f}"
        p = "-" if g["kendall_p"] is None else f"{g['kendall_p']:.3f}"
        L.append(f"| {o['id']} | {o['mean_area_km2']:.4f} | {sl} | {rel} | {p} | {g['n_years']} | {'FLAG' if o['flag'] else ''} |")
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.parse_args()
    if config.mode() != "real":
        raise SystemExit("Lake analysis runs on Earth Engine data in real mode only (QGW_MODE=real).")
    lc = config.load_yaml("lakes")
    initialize()
    full_basin = ee.Geometry(json.loads((config.raw_dir("real") / "basin.geojson").read_text()))
    dem, zone = zone_image(full_basin, lc)
    # Compute region: coarse outline of the lake zone (everything else is masked anyway).
    basin = zone.reduceToVectors(geometry=full_basin, scale=300, geometryType="polygon", maxPixels=1e9, bestEffort=True).geometry().buffer(600).intersection(full_basin, 100)
    dem, zone = zone_image(basin, lc)
    zone_km2 = ee.Image.pixelArea().divide(1e6).updateMask(zone).reduceRegion(ee.Reducer.sum(), basin, 30, maxPixels=1e10).values().get(0).getInfo()
    print(f"Lake zone {zone_km2:.0f} km2")

    L = lc["labels"]
    samples, areas = {}, {}
    for y in (L["tune_year"], L["val_year"], L["test_year"]):
        samples[y], areas[y] = sample_year(y, basin, dem, zone, lc)
        print(f"  sampled {y}: {len(samples[y])} pixels, {int(samples[y]['label'].sum())} water")
    all_blocks = sorted(set().union(*[set(a) for a in areas.values()]))
    split_of = core.block_split(all_blocks, seed=L["seed"])

    # Tune on train blocks of the tune year only.
    d = samples[L["tune_year"]]
    tr = d[d["block"].map(split_of) == "train"]
    tr_blocks = [b for b, s in split_of.items() if s == "train"]
    a = areas[L["tune_year"]]
    w = core.strata_weights(tr["label"].to_numpy().astype(bool), {1: sum(a.get(b, {}).get("water_km2", 0) for b in tr_blocks), 0: sum(a.get(b, {}).get("land_km2", 0) for b in tr_blocks)})
    ov = tr["opt_valid"].to_numpy().astype(bool)
    t_ndwi, t_nir, f1_opt = core.tune_thresholds(tr["ndwi"].to_numpy()[ov], tr["nir"].to_numpy()[ov], tr["label"].to_numpy()[ov].astype(bool), w[ov], lc["grids"]["ndwi"], lc["grids"]["nir"])
    hs = tr["vv"].to_numpy() != 0
    t_vv, f1_sar = core.tune_sar(tr["vv"].to_numpy()[hs], tr["label"].to_numpy()[hs].astype(bool), w[hs], lc["grids"]["vv_db"])
    params = {"t_ndwi": t_ndwi, "t_nir": t_nir, "t_vv": t_vv, "tune_f1_optical": f1_opt, "tune_f1_sar": f1_sar}
    print(f"  thresholds: {params}")

    evaluation = {
        "val": evaluate(samples[L["val_year"]], areas[L["val_year"]], split_of, "val", params),
        "test": evaluate(samples[L["test_year"]], areas[L["test_year"]], split_of, "test", params),
    }
    annual, masks = annual_areas(basin, dem, zone, params, lc)
    annual["comparable"] = annual["year"].isin(core.comparable_years(dict(zip(annual["year"], annual["valid_frac"], strict=True)), lc["min_valid_frac"]))
    comp_years = annual.loc[annual["comparable"], "year"].tolist()
    zone_trend = core.growth(comp_years, annual.loc[annual["comparable"], "fusion_km2"], lc["objects"]["min_years_for_trend"])

    art = config.artifact_dir("real") / "lakes"
    art.mkdir(parents=True, exist_ok=True)
    objects = {"count": 0, "top": []}
    if len(comp_years) >= 2:
        fc = lake_objects(basin, zone, masks, comp_years, lc)
        feats = []
        for i, f in enumerate(fc["features"]):
            pr = f["properties"]
            ser = [pr.get(f"a{y}", np.nan) for y in comp_years]
            g = core.growth(comp_years, ser, lc["objects"]["min_years_for_trend"])
            flag = bool(g["rel_change_per_yr"] is not None and g["rel_change_per_yr"] >= lc["objects"]["growth_flag_rel_per_yr"] and g["kendall_p"] < 0.05)
            f["properties"] = {"id": i, "areas_km2": dict(zip(map(str, comp_years), ser, strict=True)), "mean_area_km2": float(np.nanmean(ser)), "growth": g, "screening_flag": flag}
            feats.append(f)
        (art / "lake_objects.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
        ranked = sorted(feats, key=lambda f: -f["properties"]["mean_area_km2"])
        objects = {"count": len(feats), "flagged": sum(f["properties"]["screening_flag"] for f in feats),
                   "top": [{"id": f["properties"]["id"], "mean_area_km2": f["properties"]["mean_area_km2"], "growth": f["properties"]["growth"], "flag": f["properties"]["screening_flag"]} for f in ranked[:15]]}
        if ranked:
            region = ee.Geometry(ranked[0]["geometry"]).buffer(1500).bounds()
            for y in (comp_years[0], comp_years[-1]):
                overlay_png(basin, dem, y, params, lc, art / f"overlay_{y}.png", region)
            objects["overlay_region"] = region.getInfo()

    rep = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": lc, "zone_km2": zone_km2, "params": params,
        "splits": {"tune_year": L["tune_year"], "val_year": L["val_year"], "test_year": L["test_year"],
                   "blocks": {s: sum(1 for v in split_of.values() if v == s) for s in ("train", "val", "test")}},
        "evaluation": evaluation, "annual": annual.to_dict("records"), "comparable_years": comp_years,
        "zone_trend_fusion": zone_trend, "objects": objects,
        "inventory_comparison": "Hi-MAG and ICIMOD inventories not ingested (not on Earth Engine; licence and coverage to be verified). Use compare_inventory() with a local GeoJSON.",
        "sources": {"S2": "COPERNICUS/S2_SR_HARMONIZED + COPERNICUS/S2_CLOUD_PROBABILITY", "S1": "COPERNICUS/S1_GRD (IW, VV)", "DEM": DEM_ID, "labels": L["source"]},
    }
    out = config.reports_dir("real")
    (out / "lake_analysis.json").write_text(json.dumps(rep, indent=2, default=float))
    (out / "lake_analysis.md").write_text(markdown(rep), encoding="utf-8")
    print(markdown(rep))


def compare_inventory(inventory_geojson: str, objects_geojson: str) -> dict:
    """Area agreement between our lake objects and an external inventory (e.g. Hi-MAG), by overlap."""
    import geopandas as gpd

    inv = gpd.read_file(inventory_geojson).to_crs(32643)
    ours = gpd.read_file(objects_geojson).to_crs(32643)
    hits = gpd.sjoin(ours, inv, predicate="intersects")
    return {
        "inventory_lakes": len(inv),
        "our_objects": len(ours),
        "our_objects_matching_inventory": int(hits.index.nunique()),
        "inventory_area_km2": float(inv.area.sum() / 1e6),
        "our_area_km2": float(ours.area.sum() / 1e6),
    }


if __name__ == "__main__":
    main()
