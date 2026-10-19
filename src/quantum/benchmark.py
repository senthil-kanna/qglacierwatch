"""Fair quantum-classical benchmark on the 7-day discharge quantile task.

Every model gets: the same PCA inputs (fitted on training rows), the same standardised log target,
the same monotone quantile head, the same optimiser, epochs, batch size, early-stopping hold-out
and the same learning-rate grid (equal tuning budget). Intervals for every model are calibrated
with the same CQR step on the calibration period. Test is scored once per seed.

This is a noiseless state-vector SIMULATION. It can show feasibility and relative accuracy on this
task; it cannot show quantum advantage (a classical computer computed every VQC output).

Usage:
    python -m src.quantum.benchmark --mode real
    python -m src.quantum.benchmark --mode demo --quick
"""

import argparse
import json
import platform
import time
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pennylane as qml
import torch
from scipy import stats
from sklearn.decomposition import PCA

from src import config
from src.evaluate.bootstrap import block_bootstrap_diff
from src.evaluate.metrics import quantile_score, score_all
from src.evaluate.splits import issue_mask, main_splits
from src.features.build import horizon_matrix, load_latest
from src.models.calibration import CQR
from src.models.lstm import pinball_loss
from src.quantum.vqc import MLPRegressor, VQCRegressor, n_params


def prepare(table, fcfg, h, n_components):
    splits = main_splits(fcfg)

    def idx(period, embargo=True):
        m = issue_mask(table.index, period, h, embargo).to_numpy()
        sub = table.index[m]
        return sub[table.loc[sub, f"y_h{h}"].notna().to_numpy()]

    tr, ca, te = idx(splits["train"]), idx(splits["calibration"]), idx(splits["test"], embargo=False)
    X, y = horizon_matrix(table, h)
    med = X.loc[tr].median()
    mu, sd = X.loc[tr].mean(), X.loc[tr].std().replace(0, 1)
    Z = ((X.fillna(med) - mu) / sd).to_numpy()
    pca = PCA(n_components=n_components, random_state=0).fit(Z[table.index.get_indexer(tr)])
    P = pca.transform(Z)
    lo, hi = P[table.index.get_indexer(tr)].min(0), P[table.index.get_indexer(tr)].max(0)
    P = np.clip(2 * (P - lo) / (hi - lo) - 1, -1, 1)  # [-1, 1] for angle encoding pi*x
    logy = np.log(y.to_numpy())
    ymu, ysd = logy[table.index.get_indexer(tr)].mean(), logy[table.index.get_indexer(tr)].std()
    get = lambda ix: (torch.tensor(P[table.index.get_indexer(ix)], dtype=torch.float32), y.loc[ix].to_numpy())  # noqa: E731
    return {
        "train": get(tr), "cal": get(ca), "test": get(te), "test_idx": te, "train_idx": tr,
        "y_mu": ymu, "y_sd": ysd, "explained_variance": float(pca.explained_variance_ratio_.sum()),
    }


def build(spec, n_in):
    if spec["type"] == "vqc":
        return VQCRegressor(spec["n_qubits"], spec["layers"], spec["entangle"])
    return MLPRegressor(n_in, spec["hidden"])


def train_one(spec, data, qcfg, seed, lr):
    torch.manual_seed(seed)
    Xtr, ytr = data["train"]
    yz = torch.tensor((np.log(ytr) - data["y_mu"]) / data["y_sd"], dtype=torch.float32)
    idx = data["train_idx"]
    cut = idx.max() - pd.Timedelta(days=365)
    fit = np.where(idx <= cut - pd.Timedelta(days=qcfg["horizon"]))[0]
    hold = np.where(idx > cut)[0]
    model = build(spec, Xtr.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    rng = np.random.default_rng(seed)
    best, state, wait, evals, epochs = np.inf, None, 0, 0, 0
    t0 = time.perf_counter()
    for _ in range(qcfg["epochs"]):
        epochs += 1
        model.train()
        rng.shuffle(fit)
        for b in range(0, len(fit), qcfg["batch_size"]):
            bi = fit[b : b + qcfg["batch_size"]]
            opt.zero_grad()
            loss = pinball_loss(model(Xtr[bi]), yz[bi])
            loss.backward()
            opt.step()
            evals += len(bi)
        model.eval()
        with torch.no_grad():
            val = float(pinball_loss(model(Xtr[hold]), yz[hold]))
        evals += len(hold)
        if val < best - 1e-5:
            best, wait = val, 0
            state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
            if wait >= qcfg["patience"]:
                break
    model.load_state_dict(state)
    return model, {"holdout_loss": best, "train_seconds": time.perf_counter() - t0, "epochs": epochs, "forward_evals_train": evals}


def predict(model, X, data):
    with torch.no_grad():
        z = model(X).numpy()
    return np.exp(z * data["y_sd"] + data["y_mu"])


def run(mode: str, quick: bool) -> dict:
    fcfg, qcfg = config.load_yaml("forecast"), config.load_yaml("quantum")
    if quick:
        qcfg.update(seeds=qcfg["seeds"][:2], epochs=3, lr_grid=qcfg["lr_grid"][:1])
        qcfg["models"] = {k: qcfg["models"][k] for k in ("vqc", "mlp_matched", "linear")}
    table, meta = load_latest(mode)
    h = qcfg["horizon"]
    datasets = {}
    runs = []
    per_sample: dict[str, list[np.ndarray]] = {}
    for name, spec in qcfg["models"].items():
        k = spec.get("n_components", qcfg["n_components"])
        if k not in datasets:
            datasets[k] = prepare(table, fcfg, h, k)
        data = datasets[k]
        for seed in qcfg["seeds"]:
            cands = [(lr, *train_one(spec, data, qcfg, seed, lr)) for lr in qcfg["lr_grid"]]
            lr, model, info = min(cands, key=lambda c: c[2]["holdout_loss"])
            total_train = sum(c[2]["train_seconds"] for c in cands)
            cal_q = predict(model, data["cal"][0], data)
            cqr = CQR(fcfg["calibration"]["target_coverage"]).fit(data["cal"][1], cal_q)
            t0 = time.perf_counter()
            raw = predict(model, data["test"][0], data)
            infer = time.perf_counter() - t0
            calq = cqr.apply(raw)
            yt = data["test"][1]
            per_sample.setdefault(name, []).append(quantile_score(yt, calq))
            cp = model.circuit_params()
            runs.append(
                {
                    "model": name, "seed": seed, "lr": lr, "params_total": n_params(model), "params_circuit": cp,
                    "qubits": spec.get("n_qubits"), "layers": spec.get("layers"), "entangle": spec.get("entangle"),
                    "raw": score_all(yt, raw), "calibrated": score_all(yt, calq), "cqr_q_hat": cqr.q_hat,
                    "train_seconds_all_lr": total_train, "train_seconds_selected": info["train_seconds"], "epochs": info["epochs"],
                    "inference_seconds_test": infer, "n_test": len(yt),
                    "circuit_forward_evals_train": info["forward_evals_train"] if cp else 0,
                    "param_shift_equiv_evals_train": info["forward_evals_train"] * (1 + 2 * cp) if cp else 0,
                }
            )
            print(f"  {name:12s} seed {seed} lr {lr}: test QS {runs[-1]['calibrated']['qs']:.3f} cov {runs[-1]['calibrated']['coverage_80']:.3f} ({total_train:.1f}s)", flush=True)
            if name == "vqc" and seed == qcfg["seeds"][0] and not quick:
                shot_circ = model.with_shots(qcfg["shots_eval"])
                t1 = time.perf_counter()
                with torch.no_grad():
                    torch.manual_seed(0)
                    zf = model.head(torch.stack(list(shot_circ(data["test"][0], model.weights)), -1).to(torch.float32)).numpy()
                shot_q = cqr.apply(np.sort(np.exp(zf * data["y_sd"] + data["y_mu"]), axis=1))
                runs[-1]["finite_shots"] = {"shots": qcfg["shots_eval"], "calibrated": score_all(yt, shot_q), "seconds": time.perf_counter() - t1}

    df = pd.DataFrame([{**{k: v for k, v in r.items() if k not in ("raw", "calibrated", "finite_shots")}, "qs": r["calibrated"]["qs"], "coverage": r["calibrated"]["coverage_80"], "nse": r["calibrated"]["nse"]} for r in runs])
    summary = {}
    for name, g in df.groupby("model", sort=False):
        n = len(g)
        m, s = g["qs"].mean(), g["qs"].std(ddof=1) if n > 1 else float("nan")
        half = stats.t.ppf(0.975, n - 1) * s / np.sqrt(n) if n > 1 else float("nan")
        summary[name] = {
            "n_seeds": n, "qs_mean": m, "qs_sd": s, "qs_ci95": [m - half, m + half],
            "coverage_mean": g["coverage"].mean(), "nse_mean": g["nse"].mean(),
            "params_total": int(g["params_total"].iloc[0]), "params_circuit": int(g["params_circuit"].iloc[0]),
            "train_seconds_mean": g["train_seconds_all_lr"].mean(), "inference_seconds_mean": g["inference_seconds_test"].mean(),
            "circuit_forward_evals_mean": g["circuit_forward_evals_train"].mean(), "param_shift_equiv_evals_mean": g["param_shift_equiv_evals_train"].mean(),
        }
    comparisons = []
    test_n = len(datasets[qcfg["n_components"]]["test"][1])
    for other in [m for m in summary if m != "vqc"]:
        a = df[df.model == "vqc"].set_index("seed")["qs"]
        b = df[df.model == other].set_index("seed")["qs"]
        d = (a - b).dropna()
        n = len(d)
        entry = {"a": "vqc", "b": other, "paired_by": "seed", "n_seeds": n, "mean_diff": float(d.mean())}
        if n > 1:
            half = stats.t.ppf(0.975, n - 1) * d.std(ddof=1) / np.sqrt(n)
            entry.update(t_ci95=[float(d.mean() - half), float(d.mean() + half)], t_test_p=float(stats.ttest_rel(a.loc[d.index], b.loc[d.index]).pvalue))
            entry["wilcoxon_p"] = float(stats.wilcoxon(d).pvalue) if n >= 5 and (d != 0).any() else None
        if len(per_sample[other][0]) == test_n:
            la, lb = np.mean(per_sample["vqc"], axis=0), np.mean(per_sample[other], axis=0)
            entry["block_bootstrap_seed_avg"] = block_bootstrap_diff(la, lb, fcfg["bootstrap"]["block_days"], fcfg["bootstrap"]["n_resamples"], 0.95, seed=7)
        comparisons.append(entry)

    ref = {}
    fr = config.reports_dir(mode) / "forecast_results.json"
    if fr.exists():
        tp = json.loads(fr.read_text()).get("test_period", {})
        for m in ("persistence", "climatology", "gbm_quantile", "quantile_lstm"):
            if f"{m}|h{h}" in tp:
                ref[m] = tp[f"{m}|h{h}"]["calibrated"]["qs"]
    return {
        "mode": mode, "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"), "dataset_id": meta["dataset_id"],
        "target_source": meta["target_source"], "horizon": h, "quick": quick,
        "simulator": {"device": "default.qubit (PennyLane state-vector, noiseless)", "pennylane": qml.version(), "torch": torch.__version__,
                      "diff_method": "backprop (analytic expectations, shots=None)", "cpu": platform.processor(), "platform": platform.platform()},
        "inputs": {"pca_components": qcfg["n_components"], "explained_variance_train": datasets[qcfg["n_components"]]["explained_variance"], "encoding": "RY(pi*x), x scaled to [-1,1] with training min/max"},
        "protocol": {k: qcfg[k] for k in ("seeds", "epochs", "batch_size", "patience", "lr_grid")},
        "summary": summary, "comparisons": comparisons, "runs": runs, "reference_full_feature_models_qs": ref,
        "interpretation_guardrail": "Noiseless simulation on a classical CPU. Results bear on accuracy of this model class for this task, not on quantum advantage.",
    }


def markdown(rep):
    L = [f"# Quantum-classical benchmark ({rep['mode']} mode, h={rep['horizon']} days)", "", f"> {rep['interpretation_guardrail']}", "",
         f"Inputs: {rep['inputs']['pca_components']} PCA components ({rep['inputs']['explained_variance_train']:.1%} of training variance). "
         f"Seeds {rep['protocol']['seeds']}; lr grid {rep['protocol']['lr_grid']}; up to {rep['protocol']['epochs']} epochs. Simulator: {rep['simulator']['device']}, PennyLane {rep['simulator']['pennylane']}.", "",
         "| model | params (circuit) | test QS mean +/- sd | 95% CI | coverage | NSE | train s (all lr) | circuit evals (train) | param-shift equiv. |", "|---|---|---|---|---|---|---|---|---|"]
    for m, s in rep["summary"].items():
        L.append(f"| {m} | {s['params_total']} ({s['params_circuit']}) | {s['qs_mean']:.3f} +/- {s['qs_sd']:.3f} | [{s['qs_ci95'][0]:.3f}, {s['qs_ci95'][1]:.3f}] | {s['coverage_mean']:.3f} | {s['nse_mean']:.3f} | {s['train_seconds_mean']:.1f} | {s['circuit_forward_evals_mean']:.0f} | {s['param_shift_equiv_evals_mean']:.0f} |")
    L += ["", "## Paired comparisons (VQC - other; negative = VQC better)", "", "| other | mean diff | t 95% CI (seeds) | paired t p | Wilcoxon p | block-bootstrap CI (seed-avg) |", "|---|---|---|---|---|---|"]
    for c in rep["comparisons"]:
        bb = c.get("block_bootstrap_seed_avg")
        bbs = f"[{bb['lo']:.3f}, {bb['hi']:.3f}]" if bb else "n/a (different inputs)"
        tci = c.get("t_ci95")
        L.append(f"| {c['b']} | {c['mean_diff']:.3f} | {f'[{tci[0]:.3f}, {tci[1]:.3f}]' if tci else '-'} | {c.get('t_test_p', float('nan')):.3f} | {c.get('wilcoxon_p') if c.get('wilcoxon_p') is not None else '-'} | {bbs} |")
    shots = [r["finite_shots"] for r in rep["runs"] if "finite_shots" in r]
    if shots:
        s = shots[0]
        L += ["", f"Finite-shot re-evaluation of VQC (seed {rep['protocol']['seeds'][0]}, {s['shots']} shots): test QS {s['calibrated']['qs']:.3f}, coverage {s['calibrated']['coverage_80']:.3f} ({s['seconds']:.1f} s)."]
    if rep["reference_full_feature_models_qs"]:
        L += ["", "Reference (full feature set, main experiment, same test period): " + ", ".join(f"{k} {v:.3f}" for k, v in rep["reference_full_feature_models_qs"].items())]
    L += ["", "Note: with 5 seeds the smallest attainable two-sided exact Wilcoxon p-value is 0.0625."]
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default=config.mode(), choices=config.MODES)
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()
    rep = run(args.mode, args.quick)
    out = config.reports_dir(args.mode)
    out.mkdir(parents=True, exist_ok=True)
    (out / "quantum_benchmark.json").write_text(json.dumps(rep, indent=2, default=float))
    (out / "quantum_benchmark.md").write_text(markdown(rep), encoding="utf-8")
    print(markdown(rep))


if __name__ == "__main__":
    main()
