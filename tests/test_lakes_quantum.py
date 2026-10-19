import numpy as np
import pytest
import torch

from src.lakes import core
from src.quantum.vqc import MLPRegressor, VQCRegressor, n_params


def scene(seed=0, n=4000):
    """SYNTHETIC pixels: water (high NDWI, dark NIR), snow (high NDWI, bright NIR), rock."""
    rng = np.random.default_rng(seed)
    cls = rng.choice(3, size=n, p=[0.1, 0.3, 0.6])  # 0 water, 1 snow, 2 rock
    ndwi = np.select([cls == 0, cls == 1], [rng.normal(0.5, 0.1, n), rng.normal(0.35, 0.1, n)], rng.normal(-0.2, 0.1, n))
    nir = np.select([cls == 0, cls == 1], [rng.normal(0.05, 0.02, n), rng.normal(0.6, 0.1, n)], rng.normal(0.25, 0.05, n))
    vv = np.where(cls == 0, rng.normal(-22, 1.5, n), rng.normal(-10, 2, n))
    return ndwi, nir, vv, cls == 0


def test_nir_rule_separates_water_from_snow():
    ndwi, nir, _, water = scene()
    naive = ndwi > 0.2
    rule = core.optical_water(ndwi, nir, 0.2, 0.15)
    w = np.ones(len(water))
    assert core.seg_metrics(core.weighted_confusion(rule, water, w))["iou"] > 0.9
    assert core.seg_metrics(core.weighted_confusion(naive, water, w))["precision"] < 0.5


def test_metrics_edge_cases():
    m = core.seg_metrics({"tp": 0.0, "fp": 0.0, "fn": 0.0, "tn": 10.0})
    assert np.isnan(m["iou"]) and np.isnan(m["precision"])
    m = core.seg_metrics({"tp": 8.0, "fp": 2.0, "fn": 2.0, "tn": 88.0})
    assert m["iou"] == pytest.approx(8 / 12) and m["dice_f1"] == pytest.approx(16 / 20)
    assert m["area_error_frac"] == pytest.approx(0.0)


def test_stratified_weights_recover_population_rates():
    rng = np.random.default_rng(1)
    label = np.r_[np.ones(500, bool), np.zeros(500, bool)]  # balanced sample of a rare class
    pred = np.r_[rng.random(500) < 0.9, rng.random(500) < 0.01]
    w = core.strata_weights(label, {1: 1.0, 0: 99.0})  # water is 1% of the area
    m = core.seg_metrics(core.weighted_confusion(pred, label, w))
    unweighted = core.seg_metrics(core.weighted_confusion(pred, label, np.ones(1000)))
    assert m["precision"] < unweighted["precision"]  # false positives over the large land area matter
    assert m["recall"] == pytest.approx(unweighted["recall"])


def test_tuning_and_fusion():
    ndwi, nir, vv, water = scene(2)
    w = np.ones(len(water))
    t_ndwi, t_nir, f1 = core.tune_thresholds(ndwi, nir, water, w, [0.0, 0.2, 0.4], [0.1, 0.3])
    assert f1 > 0.95
    assert t_ndwi >= 0.2 and t_nir <= 0.3
    t_vv, f1s = core.tune_sar(vv, water, w, [-20, -16, -12])
    assert f1s > 0.9
    valid = np.arange(len(water)) % 2 == 0
    fused = core.fuse(core.optical_water(ndwi, nir, t_ndwi, t_nir), valid, core.sar_water(vv, t_vv))
    assert core.seg_metrics(core.weighted_confusion(fused, water, w))["iou"] > 0.85


def test_block_split_is_disjoint_and_deterministic():
    blocks = list(range(40))
    a, b = core.block_split(blocks, seed=3), core.block_split(blocks, seed=3)
    assert a == b
    assert {s for s in a.values()} == {"train", "val", "test"}
    assert sum(1 for s in a.values() if s == "train") == 20


def test_comparable_years_and_growth():
    assert core.comparable_years({2019: 0.95, 2020: 0.7, 2021: None, 2022: 0.91}, 0.9) == [2019, 2022]
    g = core.growth([2019, 2020, 2021, 2022, 2023, 2024], [0.10, 0.11, 0.12, 0.13, 0.14, 0.15])
    assert g["slope_km2_per_yr"] == pytest.approx(0.01) and g["kendall_p"] < 0.05
    assert core.growth([2019, 2020], [0.1, 0.2])["slope_km2_per_yr"] is None


def test_vqc_outputs_ordered_quantiles_and_counts_params():
    torch.manual_seed(0)
    m = VQCRegressor(n_qubits=3, layers=2, entangle=True)
    q = m(torch.rand(5, 3) * 2 - 1)
    assert q.shape == (5, 3)
    assert torch.all(q[:, 0] <= q[:, 1]) and torch.all(q[:, 1] <= q[:, 2])
    assert m.circuit_params() == 2 * 3 * 3
    assert n_params(m) == 18 + 3 * 3 + 3


def test_vqc_gradients_flow_and_mlp_matches_interface():
    m = VQCRegressor(n_qubits=2, layers=1, entangle=False)
    loss = m(torch.rand(4, 2)).sum()
    loss.backward()
    assert m.weights.grad is not None and torch.any(m.weights.grad != 0)
    mlp = MLPRegressor(4, 5)
    assert mlp(torch.rand(3, 4)).shape == (3, 3) and mlp.circuit_params() == 0
