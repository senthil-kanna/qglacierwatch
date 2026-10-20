"""Report and study-guide figures, regenerated from the committed reports and local artifacts.

Usage:
    python docs/figures/make_figures.py
Figures that need git-ignored artifacts (hindcasts, lake overlays) are skipped if those are missing.
Gauge figures use aggregate metrics only (raw NWDP data are not redistributed).
"""

import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
REP = ROOT / "reports"
INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
C = {"blue": "#2563eb", "teal": "#0d9488", "amber": "#d97706", "red": "#dc2626", "grey": "#9ca3af", "violet": "#7c3aed"}
MODEL_COLOR = {"persistence": C["grey"], "climatology": C["amber"], "gbm_quantile": C["blue"], "quantile_lstm": C["teal"]}
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.titleweight": "bold", "axes.titlesize": 11, "figure.dpi": 150, "savefig.bbox": "tight"})


def load(p):
    return json.loads((REP / p).read_text())


def box(ax, x, y, w, h, title, lines, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02", fc=color + "18", ec=color, lw=1.4))
    ax.text(x + w / 2, y + h - 0.035, title, ha="center", va="top", fontsize=9.5, weight="bold", color=INK)
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.085 - i * 0.042, ln, ha="center", va="top", fontsize=7.8, color=MUTED)


def arrow(ax, a, b, text=""):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, lw=1.2, color=INK, shrinkA=2, shrinkB=2))
    if text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.018, text, ha="center", fontsize=7.2, color=MUTED)


def architecture():
    fig, ax = plt.subplots(figsize=(13, 7.2))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.5, 0.985, "QGlacierWatch: end-to-end MLOps pipeline", ha="center", va="top", fontsize=13, weight="bold", color=INK)
    xs, w = [0.012, 0.217, 0.422, 0.627, 0.832], 0.156
    box(ax, xs[0], 0.66, w, 0.27, "1. Data sources", ["MODIS snow (EE)", "ERA5-Land weather", "GloFAS v4 discharge", "Sentinel-1/2 (lakes)", "JRC water, Hi-MAG"], C["violet"])
    box(ax, xs[1], 0.66, w, 0.27, "2. Ingest + validate", ["schema & range checks", "SHA-256 manifest", "DVC data versions", "append-only extension"], C["blue"])
    box(ax, xs[2], 0.66, w, 0.27, "3. Features", ["availability lags", "snow, melt, rain, flow", "75-day warm-up", "no look-ahead"], C["blue"])
    box(ax, xs[3], 0.66, w, 0.27, "4. Train + evaluate", ["rolling-origin CV", "GBM / LSTM / baselines", "conformal (CQR)", "bootstrap tests"], C["teal"])
    box(ax, xs[4], 0.66, w, 0.27, "5. Registry + gate", ["model cards", "coverage / NSE gate", "human approval", "rollback, audit log"], C["teal"])
    box(ax, xs[3], 0.30, w, 0.25, "6. Serve", ["FastAPI /v1/forecast", "Streamlit dashboard", "API key, rate limit"], C["amber"])
    box(ax, xs[2], 0.30, w, 0.25, "7. Monitor drift", ["season-aware detectors", "data quality rules", "residual / coverage"], C["red"])
    box(ax, xs[1], 0.30, w, 0.25, "8. Retrain policy", ["Tier 1 data fix", "Tier 2 recalibrate", "Tier 3 retrain", "Tier 4 promote"], C["red"])
    box(ax, xs[0], 0.30, w, 0.25, "Research modules", ["quantum vs classical", "glacial-lake mapping", "gauge consistency check"], C["grey"])
    for i in range(4):
        arrow(ax, (xs[i] + w + 0.012, 0.795), (xs[i + 1] - 0.012, 0.795))
    arrow(ax, (xs[4] + w / 2, 0.648), (xs[3] + w * 0.8, 0.562), "approved model")
    arrow(ax, (xs[3] - 0.012, 0.425), (xs[2] + w + 0.012, 0.425))
    arrow(ax, (xs[2] - 0.012, 0.425), (xs[1] + w + 0.012, 0.425), "alerts")
    arrow(ax, (xs[1] + w / 2, 0.562), (xs[3] + w * 0.3, 0.648))
    ax.text(0.40, 0.592, "retrain / recalibrate", fontsize=7.2, color=MUTED, rotation=10)
    ax.add_patch(FancyBboxPatch((0.01, 0.02), 0.98, 0.22, boxstyle="round,pad=0.01,rounding_size=0.02", fc="#f8fafc", ec=GRID, lw=1))
    ax.text(0.02, 0.215, "Delivery and cloud (Azure for Students; deployment pending subscription approval)", fontsize=9.5, weight="bold", color=INK, va="top")
    items = ["GitHub Actions CI: tests, lint, types, Docker build, Trivy", "GHCR: public container image", "Container Apps: API + dashboard (scale to zero)",
             "Container Apps Jobs: ingest, drift, train, lakes", "Azure Files share: data, registry, reports", "Key Vault + identity; Log Analytics, alerts, budget"]
    for i, t in enumerate(items):
        ax.text(0.025 + (i % 3) * 0.325, 0.15 - (i // 3) * 0.07, "- " + t, fontsize=8, color=INK, va="center")
    fig.savefig(OUT / "fig_architecture.png")
    plt.close(fig)


def azure():
    fig, ax = plt.subplots(figsize=(12, 6.2))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.5, 0.985, "Azure deployment design (resource group rg-qglacierwatch, Central India)", ha="center", va="top", fontsize=12, weight="bold", color=INK)
    box(ax, 0.01, 0.62, 0.2, 0.28, "GitHub", ["Actions: ci + image workflows", "GHCR public image", "OIDC for cd (optional)"], C["grey"])
    box(ax, 0.30, 0.55, 0.40, 0.35, "Container Apps environment (Consumption)", ["qgw-api: FastAPI, 0.5 vCPU / 1 GiB, 0-2 replicas", "qgw-dashboard: Streamlit, 0-1 replica",
        "Jobs: ingest (weekly), drift (weekly),", "train + lakes (manual)", "scale to zero: no charge when idle"], C["blue"])
    box(ax, 0.79, 0.62, 0.2, 0.28, "Users", ["HTTPS ingress", "X-API-Key on /v1", "dashboard (Entra auth", "before public sharing)"], C["amber"])
    box(ax, 0.30, 0.08, 0.18, 0.33, "Azure Files", ["share qgw mounted", "at /mnt/qgw", "data, registry,", "reports (uid 10001)"], C["teal"])
    box(ax, 0.52, 0.08, 0.18, 0.33, "Key Vault (RBAC)", ["qgw-api-key", "ee-service-account", "read via managed", "identity"], C["violet"])
    box(ax, 0.74, 0.08, 0.25, 0.33, "Azure Monitor", ["Log Analytics (0.2 GB/day cap)", "metric alerts: 5xx, restarts", "action group e-mail", "budget alerts 50/80/100%"], C["red"])
    box(ax, 0.01, 0.08, 0.25, 0.33, "Scripts (PowerShell)", ["preflight (read-only)", "deploy (typed confirmation)", "verify (health, auth, write)", "cleanup (tag-guarded)"], C["grey"])
    arrow(ax, (0.21, 0.76), (0.30, 0.74), "pull image")
    arrow(ax, (0.79, 0.76), (0.70, 0.74), "requests")
    arrow(ax, (0.42, 0.55), (0.40, 0.41), "mount")
    arrow(ax, (0.55, 0.55), (0.60, 0.41), "secrets")
    arrow(ax, (0.66, 0.55), (0.80, 0.41), "logs, metrics")
    fig.savefig(OUT / "fig_azure.png")
    plt.close(fig)


def forecast_series(path, split, title, name):
    p = ROOT / path
    if not p.exists():
        return
    h = pd.read_parquet(p)
    g = h[(h["split"] == split) & (h["model"] == "gbm_quantile") & (h["h"] == 7)].sort_values("target_date")
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.fill_between(g["target_date"], g["p10"], g["p90"], color=C["blue"], alpha=0.18, lw=0, label="P10-P90 interval (80%)")
    ax.plot(g["target_date"], g["p50"], color=C["blue"], lw=1.2, label="P50 forecast (7 days ahead)")
    ax.plot(g["target_date"], g["obs"], color=INK, lw=0.9, label="GloFAS target")
    ax.set_ylabel("discharge (m3/s)")
    ax.set_title(title, loc="left")
    ax.legend(frameon=False, ncol=3, loc="upper left", fontsize=8)
    fig.savefig(OUT / name)
    plt.close(fig)


def skill_bars(rep_path, title, name):
    r = load(rep_path)["test_period"]
    models = ["persistence", "climatology", "gbm_quantile", "quantile_lstm"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, metric, lab in ((axes[0], "nse", "NSE (higher is better)"), (axes[1], "coverage_80", "P10-P90 coverage (target 0.80)")):
        for i, m in enumerate(models):
            vals = [r[f"{m}|h{h}"]["calibrated"][metric] for h in (1, 7, 30)]
            ax.bar([j + i * 0.2 for j in range(3)], vals, width=0.19, color=MODEL_COLOR[m], label=m)
        ax.set_xticks([j + 0.3 for j in range(3)], ["1 day", "7 days", "30 days"])
        ax.set_title(lab, loc="left")
        if metric == "coverage_80":
            ax.axhspan(0.70, 0.90, color=C["teal"], alpha=0.10, label="gate band 0.70-0.90")
            ax.set_ylim(0, 1.05)
    handles = [Patch(color=MODEL_COLOR[m], label=m) for m in models] + [Patch(color=C["teal"], alpha=0.2, label="gate band 0.70-0.90")]
    fig.legend(handles=handles, frameon=False, fontsize=8, ncol=5, loc="lower center", bbox_to_anchor=(0.5, -0.06))
    fig.suptitle(title, x=0.01, y=1.04, ha="left", fontsize=11, weight="bold", color=INK)
    fig.savefig(OUT / name)
    plt.close(fig)


def gauge():
    r = load("real/gauge_check.json")
    s = r["glofas"]["all"]["seasons"]
    names = list(s)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    axes[0].bar(names, [s[k]["bias_ratio"] for k in names], color=[C["blue"], C["amber"], C["teal"], C["violet"]])
    axes[0].axhline(1, color=INK, lw=0.9, ls="--")
    axes[0].set_title("GloFAS / observed flow by season (1 = perfect)", loc="left")
    f23 = r["forecasts_original"]
    models = ["climatology", "gbm_quantile", "quantile_lstm"]
    x = range(len(models))
    axes[1].bar([i - 0.2 for i in x], [f23[f"{m}|h7"]["vs_glofas_same_dates"]["nse"] for m in models], width=0.38, color=C["grey"], label="vs GloFAS")
    axes[1].bar([i + 0.2 for i in x], [f23[f"{m}|h7"]["vs_gauge"]["nse"] for m in models], width=0.38, color=C["red"], label="vs gauge (Bajoura)")
    axes[1].set_xticks(list(x), models)
    axes[1].set_title("7-day forecast NSE, test 2023-2025", loc="left")
    axes[1].legend(frameon=False, fontsize=8)
    fig.text(0.01, -0.03, "Data: Himachal Pradesh Water Department via National Water Data Portal (NWIC). Aggregates only.", fontsize=7, color=MUTED)
    fig.savefig(OUT / "fig_gauge_check.png")
    plt.close(fig)


def quantum():
    s = load("fresh2026/real/quantum_benchmark.json")["summary"]
    order = sorted(s, key=lambda k: s[k]["qs_mean"])
    fig, ax = plt.subplots(figsize=(9, 3.4))
    cols = [C["violet"] if k.startswith("vqc") else C["blue"] for k in order]
    ax.barh(order, [s[k]["qs_mean"] for k in order], xerr=[s[k]["qs_sd"] for k in order], color=cols, error_kw={"ecolor": MUTED, "lw": 0.8})
    ax.invert_yaxis()
    ax.set_xlabel("test quantile score, 2026 (lower is better); bars: mean over 5 seeds, whiskers: SD")
    ax.set_title("Quantum (violet) vs classical (blue), 7-day horizon", loc="left")
    fig.savefig(OUT / "fig_quantum.png")
    plt.close(fig)


def drift():
    d = load("real/drift_replay.json")["replay"]["by_detector"]
    kinds = ["covariate", "prediction", "residual"]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    for i, det in enumerate(("baseline", "season_aware")):
        ax.bar([j + i * 0.38 for j in range(3)], [d[f"{k}|{det}"]["alert_rate"] for k in kinds], width=0.36,
               color=C["grey"] if det == "baseline" else C["teal"], label=det.replace("_", "-"))
    ax.set_xticks([j + 0.19 for j in range(3)], kinds)
    ax.set_ylabel("share of weekly checks with an alert")
    ax.set_title("Drift alerts 2016-2025: naive vs season-aware detectors", loc="left")
    ax.legend(frameon=False)
    fig.savefig(OUT / "fig_drift.png")
    plt.close(fig)


def lakes():
    r = load("real/himag_comparison.json")["primary_2017"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.3))
    axes[0].bar(["Hi-MAG lakes\n>= 0.01 km2", "found by us"], [r["himag_lakes_ge_0.01"], round(r["recall_count"] * r["himag_lakes_ge_0.01"])], color=[C["grey"], C["teal"]])
    axes[0].set_title("Detection (Hi-MAG 2017)", loc="left")
    axes[1].bar(["Hi-MAG 2017", "ours 2019"], [r["matched_area_himag_km2"], r["matched_area_ours_km2"]], color=[C["grey"], C["teal"]])
    axes[1].set_ylabel("km2")
    axes[1].set_title("Area of matched lakes", loc="left")
    fig.savefig(OUT / "fig_lakes_himag.png")
    plt.close(fig)
    ov = ROOT / "artifacts" / "real" / "lakes" / "overlay_2025.png"
    if ov.exists():
        shutil.copy(ov, OUT / "fig_lake_overlay_2025.png")


if __name__ == "__main__":
    architecture()
    azure()
    forecast_series("artifacts/fresh2026/real/hindcasts.parquet", "test", "Fresh 2026 test: GBM 7-day forecasts vs GloFAS target", "fig_forecast_2026.png")
    forecast_series("artifacts/real/hindcasts.parquet", "test", "Test 2023-2025: GBM 7-day forecasts vs GloFAS target", "fig_forecast_2023_2025.png")
    skill_bars("fresh2026/real/forecast_results.json", "Fresh 2026 test: skill and calibration", "fig_skill_2026.png")
    skill_bars("real/forecast_results.json", "Test 2023-2025: skill and calibration", "fig_skill_2023_2025.png")
    gauge()
    quantum()
    drift()
    lakes()
    print("figures written to", OUT)
