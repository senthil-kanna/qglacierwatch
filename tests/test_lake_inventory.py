"""Hi-MAG comparison logic on SYNTHETIC square lakes in a metre CRS."""

import math

import geopandas as gpd
import pytest
from shapely.geometry import box

from src.lakes.inventory import compare

CRS = "EPSG:32643"


def sq(x, y, side):
    return box(x, y, x + side, y + side)


def test_compare_counts_recall_iou_and_groups_split_lakes():
    # Reference: A (200 m square, 0.04 km2) is mapped by us as two halves; B (0.0225 km2) is missed;
    # C (0.0064 km2) is below the 0.01 km2 size floor. Ours also has one object D with no reference lake.
    ref = gpd.GeoDataFrame({"GL_ID": ["A", "B", "C"]}, geometry=[sq(0, 0, 200), sq(1000, 0, 150), sq(2000, 0, 80)], crs=CRS)
    ours = gpd.GeoDataFrame(
        {"id": [1, 2, 3], "areas_km2": [{"2019": 0.02}, {"2019": 0.02}, {"2019": 0.05}]},
        geometry=[box(0, 0, 100, 200), box(100, 0, 200, 200), sq(5000, 0, 220)], crs=CRS)
    r = compare(ours, ref)
    assert r["himag_lakes_all_sizes"] == 3 and r["himag_lakes_ge_0.01"] == 2
    assert r["recall_count"] == pytest.approx(0.5)
    assert r["recall_area"] == pytest.approx(0.04 / (0.04 + 0.0225))
    assert r["himag_missed"] == ["B"]
    assert r["our_objects_matched"] == 2 and r["our_unmatched_ids"] == [3]
    assert r["our_unmatched_area_km2"] == pytest.approx(0.05)
    # One group: our objects 1+2 vs reference A; areas summed, not double counted.
    assert r["matched_groups"] == 1
    g = r["pairs"][0]
    assert g["our_ids"] == [1, 2] and g["himag_ids"] == ["A"]
    assert g["our_area_km2"] == pytest.approx(0.04) and g["himag_area_km2"] == pytest.approx(0.04)
    # IoU of unions: intersection 0.04 km2; union = A + B + C + D.
    union = 0.04 + 0.0225 + 0.0064 + 0.0484
    assert r["polygon_iou_unions"] == pytest.approx(0.04 / union)


def test_compare_accepts_json_string_areas_and_missing_year():
    ref = gpd.GeoDataFrame({"GL_ID": ["A"]}, geometry=[sq(0, 0, 200)], crs=CRS)
    ours = gpd.GeoDataFrame({"id": [1], "areas_km2": ['{"2020": 0.03}']}, geometry=[sq(0, 0, 200)], crs=CRS)
    r = compare(ours, ref, our_year="2019")
    assert r["recall_count"] == 1.0
    assert math.isnan(r["pairs"][0]["our_area_km2"]) and math.isnan(r["pairs"][0]["ratio"])
    assert r["matched_area_ratio_median"] is None  # non-finite ratios are excluded from the median
    assert compare(ours, ref, our_year="2020")["pairs"][0]["our_area_km2"] == pytest.approx(0.03)
