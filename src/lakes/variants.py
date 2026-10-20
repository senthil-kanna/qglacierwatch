"""Lake segmentation v2: tune variants A-F on 2019 train blocks, select on 2020 validation blocks,
freeze, then score the 2021 test blocks once (docs/protocol_lakes_v2.md).

Writes configs/lakes_rule.yaml (frozen variant and thresholds) and reports/real/lake_variants.*.
The frozen rule is then used by `python -m src.lakes.pipeline --frozen-rule` for annual areas and
lake objects.

Usage:
    python -m src.lakes.variants            # real mode, Earth Engine credentials
"""

import argparse
import json
from datetime import UTC, datetime
from typing import Any

import ee
import pandas as pd
import yaml

from src import config
from src.ingest.ee_auth import initialize
from src.lakes import core
from src.lakes.pipeline import (
    block_image,
    class_areas_by_block,
    jrc_label,
    s1_composite,
    s2_composite,
    zone_image,
)

DOMAIN_MAX_SLOPE = 25  # evaluation domain D; variants apply their own, stricter slope limits
GRIDS = {"idx": [-0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "nir": [0.08, 0.12, 0.16, 0.20, 0.30], "swir": [0.03, 0.05, 0.08, 0.12]}
VV_GRID = [-22, -20, -18, -16, -14]
RULE_FILE = config.CONFIGS / "lakes_rule.yaml"
BANDS = ["ndwi", "mndwi", "nir", "swir", "opt_valid", "vv", "slope"]


def domain(lc: dict) -> dict:
    return {**lc, "max_slope_deg": DOMAIN_MAX_SLOPE}


def sample_year(year, basin, dem, zone, lc):
    comp, ndwi, nir, valid, _ = s2_composite(basin, dem, year, lc)
    mndwi = comp.normalizedDifference(["B3", "B11"]).rename("mndwi")
    swir = comp.select("B11").rename("swir")
    vv, _ = s1_composite(basin, year, lc)
    slope = ee.Terrain.slope(dem).rename("slope")
    label, block = jrc_label(year, lc), block_image(lc)
    img = (ndwi.unmask(-9).addBands(mndwi.unmask(-9)).addBands(nir.unmask(-9)).addBands(swir.unmask(-9))
           .addBands(valid.unmask(0)).addBands(vv.unmask(0)).addBands(slope).addBands(block).addBands(label).updateMask(zone))
    n = lc["labels"]["samples_per_class"]
    fc = img.stratifiedSample(numPoints=n, classBand="label", region=basin, scale=lc["scale_m"], seed=lc["labels"]["seed"] + year,
                              classValues=[0, 1], classPoints=[n, n], tileScale=8, geometries=False)
    df = pd.DataFrame([f["properties"] for f in fc.getInfo()["features"]])
    return df, class_areas_by_block(label, zone, block, basin)


def subset(df, areas, split_of, split):
    d = df[df["block"].map(split_of) == split]
    blocks = [b for b, s in split_of.items() if s == split]
    area = {1: sum(areas.get(b, {}).get("water_km2", 0) for b in blocks), 0: sum(areas.get(b, {}).get("land_km2", 0) for b in blocks)}
    lab = d["label"].to_numpy().astype(bool)
    return {c: d[c].to_numpy() for c in BANDS}, lab, core.strata_weights(lab, area), area


def score(d, lab, w, area, spec, p) -> dict:
    m = core.seg_metrics(core.weighted_confusion(core.variant_water(d, spec, p), lab, w))
    return {**m, "n": int(len(lab)), "n_water": int(lab.sum()), "label_water_km2": area[1]}


def main() -> None:
    argparse.ArgumentParser().parse_args()
    if config.mode() != "real":
        raise SystemExit("Real mode only (Earth Engine).")
    if RULE_FILE.exists():
        raise SystemExit(f"{RULE_FILE} exists: the rule is frozen and the test was scored. Do not re-run (docs/protocol_lakes_v2.md).")
    lc = domain(config.load_yaml("lakes"))
    L = lc["labels"]
    initialize()
    full = ee.Geometry(json.loads((config.raw_dir("real") / "basin.geojson").read_text()))
    dem, zone = zone_image(full, lc)
    basin = zone.reduceToVectors(geometry=full, scale=300, geometryType="polygon", maxPixels=1e9, bestEffort=True).geometry().buffer(600).intersection(full, 100)
    dem, zone = zone_image(basin, lc)

    samples, areas = {}, {}
    for y in (L["tune_year"], L["val_year"]):
        samples[y], areas[y] = sample_year(y, basin, dem, zone, lc)
        print(f"  sampled {y}: {len(samples[y])} pixels, {int(samples[y]['label'].sum())} water", flush=True)
    blocks = sorted(set(areas[L["tune_year"]]) | set(areas[L["val_year"]]))
    split_of = core.stratified_block_split({b: areas[L["tune_year"]].get(b, {}).get("water_km2", 0.0) for b in blocks}, seed=L["seed"])

    tr = subset(samples[L["tune_year"]], areas[L["tune_year"]], split_of, "train")
    hs = tr[0]["vv"] != 0
    t_vv, f1_vv = core.tune_sar(tr[0]["vv"][hs], tr[1][hs], tr[2][hs], VV_GRID)
    va = subset(samples[L["val_year"]], areas[L["val_year"]], split_of, "val")

    params: dict[str, dict[str, Any]] = {}
    val: dict[str, dict[str, Any]] = {}
    for k, spec in core.VARIANTS.items():
        if spec["sar_union"]:
            params[k] = {"params": dict(params["E"]["params"]), "train_f1": None, "note": "E thresholds reused (protocol)"}
        else:
            p, f1 = core.tune_variant(tr[0], tr[1], tr[2], spec, GRIDS, t_vv)
            params[k] = {"params": p, "train_f1": f1}
        val[k] = score(va[0], va[1], va[2], va[3], spec, params[k]["params"])
        print(f"  {k}: val IoU {val[k]['iou']:.3f} F1 {val[k]['dice_f1']:.3f} P {val[k]['precision']:.3f} R {val[k]['recall']:.3f}  {params[k]['params']}", flush=True)
    chosen = core.select_variant({k: v["iou"] for k, v in val.items()})
    print(f"  selected {chosen}", flush=True)

    # Freeze before touching the test year.
    frozen = {"variant": chosen, "spec": core.VARIANTS[chosen], "params": params[chosen]["params"], "domain_max_slope": DOMAIN_MAX_SLOPE,
              "selected_on": f"val blocks {L['val_year']} IoU", "frozen_utc": datetime.now(UTC).isoformat(timespec="seconds"),
              "protocol": "docs/protocol_lakes_v2.md"}
    RULE_FILE.write_text(yaml.safe_dump(frozen, sort_keys=False))
    art = config.artifact_dir("real") / "lakes"
    art.mkdir(parents=True, exist_ok=True)
    with open(art / "test_access.log", "a", encoding="utf-8") as fh:
        fh.write(f"{frozen['frozen_utc']} v2 test {L['test_year']} scored for A and {chosen}\n")

    samples[L["test_year"]], areas[L["test_year"]] = sample_year(L["test_year"], basin, dem, zone, lc)
    te = subset(samples[L["test_year"]], areas[L["test_year"]], split_of, "test")
    test = {k: score(te[0], te[1], te[2], te[3], core.VARIANTS[k], params[k]["params"]) for k in dict.fromkeys(["A", chosen])}

    rep = {"generated_utc": frozen["frozen_utc"], "domain": f"basin, > {lc['min_elevation_m']} m, slope < {DOMAIN_MAX_SLOPE} deg",
           "years": {"tune": L["tune_year"], "val": L["val_year"], "test": L["test_year"]},
           "blocks": {s: sum(1 for v in split_of.values() if v == s) for s in ("train", "val", "test")},
           "t_vv": t_vv, "train_f1_sar": f1_vv, "grids": GRIDS, "variants": core.VARIANTS, "params": params,
           "validation": val, "selected": chosen, "test": test}
    out = config.reports_dir("real")
    (out / "lake_variants.json").write_text(json.dumps(rep, indent=2, default=float))
    (out / "lake_variants.md").write_text(markdown(rep), encoding="utf-8")
    print(markdown(rep))


def markdown(rep: dict) -> str:
    L = [f"# Lake segmentation v2: variants (generated {rep['generated_utc']})", "",
         f"Domain: {rep['domain']}. Thresholds tuned on train blocks {rep['years']['tune']}; selection on validation blocks {rep['years']['val']}; "
         f"test blocks {rep['years']['test']} scored once after freezing. JRC labels end in 2021 and the {rep['years']['test']} test blocks were scored "
         "twice before (different domain/splits), so the test is not an untouched benchmark.", "",
         "| variant | index | slope < | SWIR guard | SAR union | thresholds | val IoU | F1 | precision | recall | area error | n (water) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in rep["validation"].items():
        s = rep["variants"][k]
        p = ", ".join(f"{a}={b:g}" for a, b in rep["params"][k]["params"].items())
        mark = " **(selected)**" if k == rep["selected"] else ""
        L.append(f"| {k}{mark} | {s['index']} | {s['max_slope']} | {'yes' if s['swir_guard'] else 'no'} | {'yes' if s['sar_union'] else 'no'} | {p} | "
                 f"{v['iou']:.3f} | {v['dice_f1']:.3f} | {v['precision']:.3f} | {v['recall']:.3f} | {v['area_error_frac']:+.1%} | {v['n']} ({v['n_water']}) |")
    L += ["", f"## Test ({rep['years']['test']}, scored once)", "", "| variant | IoU | F1 | precision | recall | area error | n (water) | JRC water km2 |", "|---|---|---|---|---|---|---|---|"]
    for k, v in rep["test"].items():
        L.append(f"| {k} | {v['iou']:.3f} | {v['dice_f1']:.3f} | {v['precision']:.3f} | {v['recall']:.3f} | {v['area_error_frac']:+.1%} | {v['n']} ({v['n_water']}) | {v['label_water_km2']:.4f} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
