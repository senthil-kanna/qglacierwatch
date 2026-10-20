// Builds docs/report/QGlacierWatch_Project_Report.docx (template: MLOps project report, Azure variant).
// Usage: node docs/report/build_report.js   (needs the npm package "docx"; set NODE_PATH if installed elsewhere)
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, ImageRun, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, LevelFormat, PageBreak, TableOfContents, Footer, PageNumber, Header,
} = require("docx");

const ROOT = path.resolve(__dirname, "..", "..");
const FIG = path.join(ROOT, "docs", "figures");
const FONT = "Arial";
const W = 9026; // A4 width minus 1-inch margins, DXA

// ---------- helpers ----------
const p = (text, opts = {}) => new Paragraph({ spacing: { after: 120, line: 300 }, alignment: opts.align || AlignmentType.JUSTIFIED,
  children: runs(text, opts) });
function runs(text, opts = {}) {
  // **bold** segments
  return String(text).split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((s) => s.startsWith("**")
    ? new TextRun({ text: s.slice(2, -2), bold: true, font: FONT, size: opts.size || 22, italics: opts.italics })
    : new TextRun({ text: s, font: FONT, size: opts.size || 22, italics: opts.italics, color: opts.color }));
}
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 240, after: 160 }, children: [new TextRun({ text: t, font: FONT })] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 120 }, children: [new TextRun({ text: t, font: FONT })] });
const bullet = (t) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60, line: 280 }, children: runs(t) });
const pb = () => new Paragraph({ children: [new PageBreak()] });
const note = (t) => new Paragraph({ spacing: { before: 80, after: 160 }, shading: { type: ShadingType.CLEAR, fill: "EEF4FB", color: "auto" },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color: "2563EB", space: 6 } }, children: runs(t, { size: 20 }) });

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function figure(file, caption, widthPx = 600) {
  const f = path.join(FIG, file);
  if (!fs.existsSync(f)) return [p(`[Figure missing: ${file}]`)];
  const s = pngSize(f);
  const h = Math.round((widthPx * s.h) / s.w);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(f), transformation: { width: widthPx, height: h },
        altText: { title: caption, description: caption, name: file } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: caption, italics: true, font: FONT, size: 18, color: "4B5563" })] }),
  ];
}
const border = { style: BorderStyle.SINGLE, size: 4, color: "C7CED9" };
function table(header, rows, widths, caption) {
  const total = widths.reduce((a, b) => a + b, 0);
  const cell = (t, isHead) => new TableCell({
    borders: { top: border, bottom: border, left: border, right: border }, width: { size: 0, type: WidthType.DXA },
    shading: isHead ? { fill: "E8EEF6", type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children: [new Paragraph({ children: runs(t, { size: 18 }).map((r) => r) })],
  });
  const mk = (cells, isHead) => new TableRow({ tableHeader: isHead, children: cells.map((c, i) => {
    const tc = cell(c, isHead); tc.options = tc.options || {}; return new TableCell({
      borders: { top: border, bottom: border, left: border, right: border }, width: { size: widths[i], type: WidthType.DXA },
      shading: isHead ? { fill: "E8EEF6", type: ShadingType.CLEAR, color: "auto" } : undefined,
      margins: { top: 60, bottom: 60, left: 90, right: 90 },
      children: [new Paragraph({ children: isHead ? [new TextRun({ text: c, bold: true, font: FONT, size: 18 })] : runs(c, { size: 18 }) })] }); }) });
  const out = [new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: widths, rows: [mk(header, true), ...rows.map((r) => mk(r, false))] })];
  if (caption) out.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200 }, children: [new TextRun({ text: caption, italics: true, font: FONT, size: 18, color: "4B5563" })] }));
  return out;
}

// ---------- results loaded from the repository (no hand-copied numbers where a file exists) ----------
// Python's json writes NaN/Infinity, which JSON.parse rejects; map them to null.
const J = (p_) => JSON.parse(fs.readFileSync(path.join(ROOT, "reports", p_), "utf8").replace(/\b(-?Infinity|NaN)\b/g, "null"));
const fr26 = J("fresh2026/real/forecast_results.json").test_period;
const fr23 = J("real/forecast_results.json").test_period;
const q26 = J("fresh2026/real/quantum_benchmark.json").summary;
const gauge = J("real/gauge_check.json");
const himag = J("real/himag_comparison.json").primary_2017;
const lv = J("real/lake_variants.json");
const lt = J("real/loadtest_local_uvicorn.json");
const f = (x, d = 3) => (x === null || x === undefined || Number.isNaN(x) ? "-" : Number(x).toFixed(d));
const MODELS = ["persistence", "climatology", "gbm_quantile", "quantile_lstm"];
const fcRows = (fr) => MODELS.map((m) => [m, ...[1, 7, 30].map((h) => {
  const c = fr[`${m}|h${h}`].calibrated; return `${f(c.nse)} / ${f(c.coverage_80, 2)}`; })]);
const seqF = lt.sequential_forecast;
const conc = lt.concurrent_forecast;
const maxRps = Math.max(...conc.map((c) => c.throughput_rps));

// ---------- content ----------
const TITLE = "A Season-Aware, Drift-Governed MLOps Pipeline for Probabilistic Snowmelt-River Discharge Forecasting in the Beas Basin Using Serverless Azure Container Apps";

const titlePage = [
  new Paragraph({ spacing: { before: 1800 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "3rd Semester Lab Project Report", font: FONT, size: 24, color: "4B5563" })] }),
  new Paragraph({ spacing: { before: 400, after: 400 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: TITLE, bold: true, font: FONT, size: 36, color: "1F3A5F" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Project: QGlacierWatch", font: FONT, size: 24 })] }),
  new Paragraph({ spacing: { before: 900 }, alignment: AlignmentType.CENTER, children: runs("Submitted by: [Student name]  |  Register number: [Register number]", { size: 24 }) }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: runs("Guide: [Guide name, designation]", { size: 24 }) }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: runs("Department of [Department], [College / University]", { size: 24 }) }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: runs("[Month Year]", { size: 24 }) }),
  pb(),
  h1("Acknowledgement and data credits"),
  p("Data used in this project: MODIS MOD10A1 snow cover (NASA), ERA5-Land reanalysis (ECMWF, Copernicus Climate Change Service), GloFAS v4 river discharge (Copernicus Emergency Management Service, via Open-Meteo), Sentinel-1 and Sentinel-2 imagery (Copernicus), JRC Global Surface Water, the Hi-MAG glacial lake inventory (Chen et al., CC BY 4.0), and river discharge telemetry of the Himachal Pradesh Water Department obtained from the National Water Data Portal (National Water Informatics Centre, Ministry of Jal Shakti). Satellite processing used Google Earth Engine."),
  note("[Edit as required by your institution] Declaration of AI assistance: the software, analyses and drafts of this report were developed with the help of an AI coding assistant (Claude, Anthropic). All numerical results were produced by the code in the project repository and can be reproduced from it."),
  pb(),
  h1("Contents"),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  p("(Right-click the table of contents in Word and choose Update Field to refresh page numbers.)", { size: 18, italics: true }),
  pb(),
];

const sec1 = [h1("1. Project Title"), p(`**${TITLE}.**`),
  p("The title names the machine learning goal (probabilistic discharge forecasting with uncertainty intervals for a snow- and glacier-fed river), the operational mechanism (season-aware drift detection with governed retraining) and the cloud runtime (Azure Container Apps, the serverless container platform used instead of AWS Lambda; see Section 4).")];

const sec2 = [h1("2. Abstract"),
  p(`Himalayan snow-fed rivers such as the Beas need reliable short- and medium-range discharge forecasts, but machine learning forecasts degrade silently as seasons, weather regimes and input data change, and observed gauge data are restricted. We built QGlacierWatch, an end-to-end MLOps pipeline that forecasts daily discharge 1, 7 and 30 days ahead as P10/P50/P90 intervals using LightGBM quantile regression and a quantile LSTM with conformalized quantile regression, from MODIS snow cover and ERA5-Land weather, against GloFAS v4 modelled discharge. It adds versioned data lineage, a gated model registry with human approval, season-aware drift detection with tiered retraining, an API and a dashboard. The cloud topology is GitHub Actions CI publishing a container image to GitHub Container Registry, Azure Container Apps for the API and dashboard with scale-to-zero, Container Apps Jobs for ingestion, drift checks and training, Azure Files, Key Vault and Azure Monitor alerts; it is built and tested, with deployment pending subscription activation. On a fresh, untouched 2026 test the selected model reached NSE ${f(fr26["gbm_quantile|h1"].calibrated.nse)}, ${f(fr26["gbm_quantile|h7"].calibrated.nse)} and ${f(fr26["gbm_quantile|h30"].calibrated.nse)}, but its intervals over-covered and failed the gate; against a nearby observed telemetry gauge, skill dropped to NSE 0.1-0.3. The local API served forecasts with a median latency of ${f(seqF.p50_ms, 0)} ms.`)];

const sec3 = [h1("3. Introduction & Research Gap"), h2("3.1 Background & Motivation"),
  p("The Beas River above Bhuntar (Himachal Pradesh, catchment about 3,532 km2) is fed by seasonal snow, glaciers and the summer monsoon. Discharge forecasts matter for hydropower operation at downstream projects, flood preparedness (the Beas valley was badly affected in July 2023) and water management. Snowmelt-dominated rivers are a hard forecasting problem: the relationship between snow, temperature, rain and flow changes through the year, and the climate is shifting."),
  p("A model that is trained once and deployed statically fails in predictable ways. (1) **Seasonal and regime shift:** a model calibrated on calm years under-states uncertainty in an extreme year and over-states it in a dry one; we observed both (Section 5). (2) **Silent input problems:** cloud gaps in MODIS snow, revised reanalysis values or a changed discharge product alter the inputs without any error being raised; we found that the GloFAS series used as the target switched from reanalysis to forecast-derived values on 2023-08-05. (3) **No accountability:** without a registry and a gate, a worse model can replace a better one, and nobody can say which data and code produced a forecast. (4) **Uncalibrated uncertainty:** point forecasts without reliable intervals cannot support decisions. MLOps practices (versioned data, automated evaluation, monitored drift, governed retraining and reproducible deployment) address these failures [1], [2]."),
  p("Observed discharge for the Beas at Bhuntar (Central Water Commission) is classified for the Indus basin. The project therefore uses GloFAS v4 modelled discharge [7], [12] as the forecast target and checks it against the only open telemetry gauge found nearby (Section 5.4)."),
  h2("3.2 Related Work Matrix"),
  p("Recent peer-reviewed work shows strong data-driven hydrological models, but the operational loop around them (versioned lineage, calibrated intervals with a promotion gate, drift-triggered retraining, low-cost deployment) is usually not part of the published study:"),
  ...table(["Author & Year", "ML Model Target", "Deployment Stack / Infrastructure", "Gap relevant to this project"], [
    ["Nearing et al. (2024) [4]", "LSTM, global river discharge and extreme-flood prediction (compared with GloFAS)", "Operational global service (Google Flood Hub)", "Global model on proprietary infrastructure; per-basin calibrated intervals, promotion gate and drift-triggered retraining for a single small basin are not part of the study."],
    ["Auer et al. (2024) [6]", "LSTM with conformal prediction for hydrological uncertainty intervals", "Research code (offline experiments)", "Studies interval quality; deployment, monitoring and retraining are outside its scope."],
    ["Chen, Huang & Huang (2023) [5]", "Coupled SWAT-LSTM, daily streamflow in data-scarce watersheds", "Offline model study", "No operational pipeline, uncertainty intervals or drift handling reported."],
    ["Our Team (2026)", "LightGBM quantile + quantile LSTM with CQR; persistence and climatology baselines; simulated VQC benchmark", "GitHub Actions + GHCR + Azure Container Apps (API, dashboard, jobs) + Azure Files + Key Vault + Azure Monitor", "Season-aware drift detection, tiered retraining, promotion gate with human approval, append-only versioned data, scale-to-zero serverless serving."],
  ], [1700, 2150, 2250, 2926], "Table 1. Related work and the gap this project addresses."),
];

const sec4 = [h1("4. System Architecture & Azure Methodology"),
  note("**Cloud platform note.** The template is written for AWS. This project uses Microsoft Azure (Azure for Students credit, USD 100, no card) with the same architectural roles. Table 2 maps each AWS service named in the template to the Azure service used. **Deployment status:** all infrastructure is defined as code and tested; the resources are not yet created because the student subscription is awaiting activation. Live URLs and cloud measurements will be added after deployment."),
  ...table(["Template role (AWS)", "This project (Azure / open tools)", "Why"], [
    ["Amazon S3 + Object Versioning", "Azure Files share mounted at /mnt/qgw; DVC data versions + SHA-256 manifest", "Container Apps can mount Azure Files directly (no code change); DVC gives versioned lineage across machines"],
    ["SageMaker Pipelines", "Python pipeline (src.pipeline.train) run as a Container Apps Job; GitHub Actions CI", "No Azure ML compute cost; same image locally and in the cloud"],
    ["SageMaker Model Registry", "File registry on the share: model cards, gate, approval, rollback, audit log", "Zero cost; full lineage (dataset id, code commit, config)"],
    ["AWS Lambda + API Gateway", "Azure Container Apps (HTTPS ingress, min replicas 0, revisions)", "Serverless containers that scale to zero; heavy ML libraries do not fit Lambda-style limits"],
    ["Amazon CloudWatch / Model Monitor", "Azure Monitor: Log Analytics + metric alerts + action group; weekly drift job", "Metric alerts do not wake a scaled-to-zero app"],
    ["Amazon ECR", "GitHub Container Registry (public)", "Free; built by CI"],
    ["AWS Secrets Manager / IAM", "Azure Key Vault (RBAC) + user-assigned managed identity", "No secrets in images or code"],
    ["AWS Budgets", "Azure Consumption budget (alerts at 50%, 80%, 100%)", "Protects the student credit"],
  ], [2300, 3600, 3126], "Table 2. AWS services named in the template and the Azure services used."),
  h2("4.1 Pipeline Architecture Diagram"),
  ...figure("fig_architecture.png", "Figure 1. End-to-end pipeline: ingestion, validation, features, training, registry, serving, drift monitoring and retraining.", 620),
  ...figure("fig_azure.png", "Figure 2. Azure deployment design (resource group rg-qglacierwatch, region Central India).", 620),
  h2("4.2 Data Ingestion & Lineage Control"),
  p("Inputs are pulled by code, never edited by hand: daily basin-mean MODIS snow cover and ERA5-Land weather from Google Earth Engine, GloFAS v4 discharge from the Open-Meteo Flood API, and monthly per-cell snow maps. Every raw file passes schema and range validation and is recorded in a SHA-256 manifest; a refresh job refuses to overwrite a recorded file whose bytes changed, because that would silently change the data a model was trained on. Data versions are tracked with DVC and pushed to a remote; extending the record (for example adding 2026) creates a new append-only version whose old values are byte-identical copies."),
  p("In Azure the same directory layout lives on one Azure Files share mounted into every container: **data/raw/** (inputs + manifest), **data/processed/** (feature tables named by dataset id), **artifacts/** (model registry, model bundles, hindcasts) and **reports/**. Lineage is carried by identifiers rather than by storage versioning: each feature table has a dataset id, each model card records the dataset id, code commit, configuration and seeds, and each report states which ones it used. Blob Storage with object versioning is the alternative if the share is later replaced; it was not used because Container Apps cannot mount Blob Storage."),
  h2("4.3 Continuous Training (CT) Orchestration"),
  bullet("**Model selection:** rolling-origin cross-validation over four validation years with a fixed, pre-registered grid (4 LightGBM configurations, 2 LSTM configurations); selection by mean quantile score only."),
  bullet("**Training:** three seeds per model; forecast = mean of seed quantiles."),
  bullet("**Calibration:** conformalized quantile regression [10], fitted per season on a separate calibration period."),
  bullet("**Evaluation:** a held-out test period scored once and logged; paired block-bootstrap comparisons against persistence and climatology."),
  bullet("**Registry and gate:** every candidate is registered with a model card; promotion needs NSE floors, P10-P90 coverage within 0.70-0.90, beating climatology, at least 180 samples, at least 2% better than the incumbent, and a named human approver. Rollback restores the previous model with an audit-log entry."),
  bullet("**In Azure:** the training job (2 vCPU, 4 GiB) is a manual Container Apps Job; ingestion and drift run weekly on a schedule. Retraining is triggered by policy tiers (Section 4.5), not on every run."),
  h2("4.4 Serverless Inference Microservice Deployment"),
  p("The API (FastAPI) and the dashboard (Streamlit) run from one container image as two Azure Container Apps with **minReplicas 0**: no compute is billed while they are idle, and the first request after idle starts a replica (cold start). The API exposes /health, /v1/forecast (P10/P50/P90 for 1/7/30 days with provenance), /v1/hindcast, /v1/models and /v1/reports; /v1 routes need an API key held in Key Vault, and a per-client rate limit applies. Liveness and readiness probes use /health. The API scales to at most two replicas on concurrent HTTP load (30 per replica) and keeps revisions for one-command rollback. Compared with Lambda + API Gateway, Container Apps runs the full Python ML stack (LightGBM, PyTorch) without package-size limits and still bills per second only when running."),
  p("**Estimated cost** (Azure retail prices, Central India, retrieved 2026-10-20; estimates, not guarantees): Container Apps and Jobs inside the monthly free grant (180,000 vCPU-s, 360,000 GiB-s, 2 M requests); Azure Files about USD 0.01; Key Vault under USD 0.01; Log Analytics inside 5 GB free; metric alerts about USD 0.20 or less; total about USD 0-1 per month."),
  h2("4.5 Automated Monitoring & Drift Loop"),
  p("A weekly drift job compares the latest inputs, predictions and residuals with season-matched reference windows, so normal seasonal change is not mistaken for drift. Data-quality rules catch stale or missing inputs. Alerts map to tiers: Tier 1 fix the data; Tier 2 recalibrate the conformal offsets on recent data; Tier 3 retrain a candidate (only for persistent residual drift) and compare it with the incumbent on the same window; Tier 4 promote, which still needs the gate and a human approver. In Azure, platform metric alerts on the API (5xx responses, container restarts) e-mail the owner through an action group; logs go to Log Analytics with a daily cap. A synthetic availability ping was rejected: it would keep the scale-to-zero app awake and cost about USD 11 per month."),
];

const t5rows = [
  ["Model validation (NSE, 7-day, 2026 test)", `${f(fr26["gbm_quantile|h7"].calibrated.nse)} (same model file)`, "Same model artifact; deployment pending"],
  ["P50 inference latency (/v1/forecast)", `${f(seqF.p50_ms, 1)} ms (sequential, 1 process)`, "Pending deployment"],
  ["P95 inference latency", `${f(seqF.p95_ms, 1)} ms sequential; ${f(conc[3].p95_ms, 0)} ms at 32 concurrent users`, "Pending deployment"],
  ["Concurrent request throughput", `${f(maxRps, 1)} req/s peak, ${f(conc[3].throughput_rps, 1)} req/s at 32 users, 0 errors`, "Pending deployment (scales to 2 replicas)"],
  ["Drift detection & alert time", "Manual inspection (days to weeks)", "Weekly scheduled job (check runs in about 3 s); metric alerts evaluated every 5 min"],
];

const sec5 = [h1("5. Experimental Setup & Results"), h2("5.1 Setup"),
  ...table(["Item", "Setting"], [
    ["Basin and target", "Beas above Bhuntar, HydroBASINS level 8 (3,532 km2); GloFAS v4 at 31.825 N, 77.125 E (reanalysis to 2023-08-04, forecast-derived after)"],
    ["Inputs", "MODIS MOD10A1 snow cover, ERA5-Land (temperature, precipitation, snowmelt, SWE), lagged discharge; availability lags 1/1/5 days"],
    ["Horizons and outputs", "1, 7 and 30 days; P10, P50, P90"],
    ["Models", "Persistence, day-of-year climatology, LightGBM quantile, quantile LSTM; simulated variational quantum circuit (benchmark)"],
    ["Splits (main)", "Train 2015-2020, calibration 2021-2022, test 2023-2025"],
    ["Splits (fresh test)", "Train 2015-2023, calibration 2024-2025, test Jan-Sep 2026 (registered before data were added, scored once)"],
    ["Metrics", "NSE, KGE, MAE, RMSE, quantile score (QS), P10-P90 coverage and width, seasonal breakdown, block bootstrap"],
    ["Hardware", "Windows 11, 16 logical CPUs, 24 GB RAM, no GPU; Python 3.12"],
  ], [2400, 6626], "Table 3. Experimental setup."),
  h2("5.2 Forecast accuracy and calibration"),
  ...table(["Model", "1 day: NSE / cov80", "7 days: NSE / cov80", "30 days: NSE / cov80"], fcRows(fr23), [2600, 2142, 2142, 2142], "Table 4. Test 2023-2025 (per-season conformal calibration). Coverage target 0.80, gate band 0.70-0.90."),
  ...table(["Model", "1 day: NSE / cov80", "7 days: NSE / cov80", "30 days: NSE / cov80"], fcRows(fr26), [2600, 2142, 2142, 2142], "Table 5. Fresh test January-September 2026, scored once."),
  ...figure("fig_skill_2026.png", "Figure 3. Fresh 2026 test: NSE and interval coverage by model and horizon.", 600),
  ...figure("fig_forecast_2026.png", "Figure 4. 7-day forecasts (P50 and P10-P90) against the GloFAS target, 2026.", 600),
  p("The learned models reproduce GloFAS very well (NSE 0.96-0.99 in 2026) and beat climatology at 1 and 7 days; at 1 day nothing beats persistence. **No model passed the promotion gate:** in 2023-2025 the 30-day intervals were too narrow (coverage 0.689), and in 2026 they were too wide (0.938 at 1 day, 0.955 at 30 days) because calibration on the extreme 2025 flows widened them for a low-flow 2026. This is the main weakness of conformal calibration when calibration and test years differ."),
  h2("5.3 Infrastructure evaluation"),
  ...table(["Infrastructure Evaluation Metric", "Baseline manual setup (local uvicorn, measured)", "Proposed cloud-native pipeline (Azure Container Apps)"], t5rows, [2800, 3200, 3026],
    "Table 6. Operational parameters. Local values measured with scripts/loadtest.py (200 sequential requests; 20 s closed-loop runs at 1, 4, 16, 32 users; rate limit lifted for the test only). Cloud values will be measured with the same script after deployment."),
  ...figure("fig_drift.png", "Figure 5. Share of weekly checks with an alert, 2016-2025: naive vs season-aware detectors.", 520),
  p("Season-aware detectors cut covariate alerts from 99.8% to 4.9% of weekly checks, which makes alerts usable. On controlled synthetic faults they detected 42-100% of events with median delays of 14-42 days, against 100% detection but no precision for the naive detectors (they alarm on every clean window as well)."),
  h2("5.4 Consistency check against an observed gauge"),
  p(`GloFAS was compared with telemetry from Bajoura Bridge (Himachal Pradesh Water Department, via the National Water Data Portal), 3.7 km downstream of the outlet: ${gauge.quality.valid_days} valid days between ${gauge.quality.first_day} and ${gauge.quality.last_day}. GloFAS matched the gauge poorly (NSE ${f(gauge.glofas.all.overall.nse, 2)}, about half the observed flow in 2026), and the forecasts reached only NSE 0.1-0.3 against the gauge. Because the station's measurement method and quality control are unknown, this is a consistency check, not validation; it shows that the reported skill is skill at reproducing GloFAS.`),
  ...figure("fig_gauge_check.png", "Figure 6. GloFAS vs observed flow by season, and 7-day forecast NSE against GloFAS and against the gauge.", 600),
  h2("5.5 Research modules"),
  ...table(["Model (7-day, 2026 test)", "Parameters (circuit)", "Quantile score (mean +/- SD, 5 seeds)", "NSE"],
    ["vqc", "vqc_noent", "vqc_6q", "vqc_1layer", "linear", "mlp_matched", "mlp_large"].map((k) => [k, `${q26[k].params_total} (${q26[k].params_circuit})`, `${f(q26[k].qs_mean, 2)} +/- ${f(q26[k].qs_sd, 2)}`, f(q26[k].nse_mean, 3)]),
    [2600, 2000, 2700, 1726], "Table 7. Simulated quantum vs classical benchmark (noiseless simulator; lower QS is better)."),
  p("The simulated quantum model was worse than all classical models of similar size (paired t-test p <= 0.005). A noiseless simulation says nothing about quantum advantage; the result is about this model class on this task."),
  p(`**Glacial lakes:** Sentinel-1/2 water mapping against JRC labels reached validation IoU ${f(lv.validation.A.iou)} and test IoU ${f(lv.test.A.iou)}; a registered comparison of five alternative rules (MNDWI, slope limits, SWIR guard, SAR union) found none better. Against the Hi-MAG inventory (2017) the pipeline found ${Math.round(himag.recall_count * himag["himag_lakes_ge_0.01"])} of ${himag["himag_lakes_ge_0.01"]} lakes of at least 0.01 km2, but matched lake areas were about half of Hi-MAG's.`),
  ...figure("fig_lakes_himag.png", "Figure 7. Lake detection and matched area against the Hi-MAG inventory.", 480),
];

const sec6 = [h1("6. Conclusion & Future Enhancements"),
  p("**Achievements.** The project delivers a reproducible MLOps pipeline for a data-scarce Himalayan river: versioned, validated data; leakage-free training and evaluation with pre-registered protocols; calibrated probabilistic forecasts; a registry with a promotion gate, human approval and rollback; season-aware drift detection with tiered retraining; an API and dashboard; continuous integration (tests, type checks, container build and vulnerability scan); and an Azure deployment that is defined as code, cost-capped and tested, awaiting subscription activation. Results are reported honestly, including failures: no model passed the gate, and the target itself departs strongly from the one open gauge."),
  p("**Technical constraint.** Orchestration is a set of independent Container Apps Jobs sharing one file share. Jobs are not chained (ingest, then features, then drift, then a conditional retrain), and the file-based registry assumes one writer at a time. A failed step does not automatically stop or retry the next one."),
  p("**Proposed enhancement for the next cohort.** Replace the independent jobs with an orchestrated workflow: Azure Durable Functions or Logic Apps (the Azure counterparts of AWS Step Functions) to chain ingest, validation, drift check and conditional retraining with retries and approvals; or Azure ML pipelines with its model registry if a compute budget is available; or AKS for multi-model serving at scale (comparable to Amazon EKS). On the science side, the largest gains would come from observed discharge (a formal request to the Central Water Commission), adaptive conformal methods across hydrological regimes, and post-2021 lake reference data."),
];

const refs = [
  'D. Kreuzberger, N. Kühl, and S. Hirschl, "Machine learning operations (MLOps): Overview, definition, and architecture," IEEE Access, vol. 11, pp. 31866-31879, 2023, doi: 10.1109/ACCESS.2023.3262138.',
  'O. A. Mahdi, N. Ali, E. Pardede, A. Alazab, T. Al-Quraishi, and B. Das, "Roadmap of concept drift adaptation in data stream mining, years later," IEEE Access, vol. 12, pp. 21129-21146, 2024, doi: 10.1109/ACCESS.2024.3358817.',
  'D. Lukats, O. Zielinski, A. Hahn, and F. Stahl, "A benchmark and survey of fully unsupervised concept drift detectors on real-world data streams," Int. J. Data Sci. Anal., vol. 19, no. 1, pp. 1-31, 2025, doi: 10.1007/s41060-024-00620-y.',
  'G. Nearing et al., "Global prediction of extreme floods in ungauged watersheds," Nature, vol. 627, no. 8004, pp. 559-563, 2024, doi: 10.1038/s41586-024-07145-1.',
  'S. Chen, J. Huang, and J.-C. Huang, "Improving daily streamflow simulations for data-scarce watersheds using the coupled SWAT-LSTM approach," J. Hydrol., vol. 622, Art. no. 129734, 2023, doi: 10.1016/j.jhydrol.2023.129734.',
  'A. Auer, M. Gauch, F. Kratzert, G. Nearing, S. Hochreiter, and D. Klotz, "A data-centric perspective on the information needed for hydrological uncertainty predictions," Hydrol. Earth Syst. Sci., vol. 28, no. 17, pp. 4099-4126, 2024, doi: 10.5194/hess-28-4099-2024.',
  'C. Prudhomme et al., "Global hydrological reanalyses: The value of river discharge information for world-wide downstream applications - The example of the Global Flood Awareness System GloFAS," Meteorol. Appl., vol. 31, no. 2, Art. no. e2192, 2024, doi: 10.1002/met.2192.',
  'J. Cunningham and J. Zhuang, "Investigating and mitigating barren plateaus in variational quantum circuits: A survey," Quantum Inf. Process., vol. 24, no. 2, 2025, doi: 10.1007/s11128-025-04665-1.',
  'F. Kratzert, D. Klotz, C. Brenner, K. Schulz, and M. Herrnegger, "Rainfall-runoff modelling using long short-term memory (LSTM) networks," Hydrol. Earth Syst. Sci., vol. 22, no. 11, pp. 6005-6022, 2018, doi: 10.5194/hess-22-6005-2018.',
  'Y. Romano, E. Patterson, and E. Candès, "Conformalized quantile regression," in Proc. Adv. Neural Inf. Process. Syst. (NeurIPS), vol. 32, 2019.',
  'G. Ke et al., "LightGBM: A highly efficient gradient boosting decision tree," in Proc. Adv. Neural Inf. Process. Syst. (NIPS), vol. 30, 2017, pp. 3146-3154.',
  'S. Harrigan et al., "GloFAS-ERA5 operational global river discharge reanalysis 1979-present," Earth Syst. Sci. Data, vol. 12, no. 3, pp. 2043-2060, 2020, doi: 10.5194/essd-12-2043-2020.',
  'J. Muñoz-Sabater et al., "ERA5-Land: A state-of-the-art global reanalysis dataset for land applications," Earth Syst. Sci. Data, vol. 13, no. 9, pp. 4349-4383, 2021, doi: 10.5194/essd-13-4349-2021.',
  'F. Chen et al., "Annual 30 m dataset for glacial lakes in High Mountain Asia from 2008 to 2017," Earth Syst. Sci. Data, vol. 13, no. 2, pp. 741-766, 2021, doi: 10.5194/essd-13-741-2021.',
  'H. V. Gupta, H. Kling, K. K. Yilmaz, and G. F. Martinez, "Decomposition of the mean squared error and NSE performance criteria: Implications for improving hydrological modelling," J. Hydrol., vol. 377, no. 1-2, pp. 80-91, 2009, doi: 10.1016/j.jhydrol.2009.08.003.',
];
const sec7 = [h1("7. References"), ...refs.map((r, i) => new Paragraph({ spacing: { after: 100, line: 276 }, indent: { left: 567, hanging: 567 },
  children: [new TextRun({ text: `[${i + 1}]\t`, font: FONT, size: 20 }), new TextRun({ text: r, font: FONT, size: 20 })] }))];

const shots = [
  ["screens/dash_1_forecast.png", "Figure A1. Dashboard - forecast from the latest data and historical replay."],
  ["screens/dash_2_skill.png", "Figure A2. Dashboard - skill and calibration."],
  ["screens/dash_3_basin.png", "Figure A3. Dashboard - basin map, snow cover chart and monthly snow-cover map."],
  ["screens/dash_4_lakes.png", "Figure A4. Dashboard - glacial lakes."],
  ["screens/dash_5_drift.png", "Figure A5. Dashboard - drift monitoring."],
  ["screens/dash_6_governance.png", "Figure A6. Dashboard - model registry and retraining."],
  ["screens/dash_7_quantum.png", "Figure A7. Dashboard - quantum benchmark."],
  ["screens/api_1_docs.png", "Figure A8. REST API interactive documentation (/docs)."],
  ["screens/api_3_forecast.png", "Figure A9. REST API forecast response (/v1/forecast)."],
];
const appendix = [h1("Appendix A. System outputs (screenshots)"), p("Screenshots of the running system (local run on real data, 2026-10-20)."),
  ...shots.flatMap(([file, cap]) => figure(file, cap, 560)),
  h1("Appendix B. Reproducing the results"),
  p("All code, configuration, protocols and reports are in the project repository. Main commands (Python 3.12, from the repository root):"),
  ...["python -m pip install -r requirements-dev.txt", "python -m pytest", "python -m src.pipeline.train --mode real --final",
    "python -m src.drift.replay --mode real", "python -m src.quantum.benchmark --mode real", "uvicorn api.main:app --port 8000",
    "streamlit run dashboard/streamlit_app.py", "./scripts/azure/preflight.ps1 -ImageTag <git-sha>   (after Azure activation)"].map((c) =>
    new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: c, font: "Consolas", size: 18 })] })),
];

const doc = new Document({
  creator: "QGlacierWatch", title: TITLE,
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 30, bold: true, font: FONT, color: "1F3A5F" }, paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 25, bold: true, font: FONT, color: "2563EB" }, paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 567, hanging: 283 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "QGlacierWatch - MLOps project report", font: FONT, size: 16, color: "6B7280" })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 })] })] }) },
    children: [...titlePage, ...sec1, ...sec2, ...sec3, pb(), ...sec4, pb(), ...sec5, pb(), ...sec6, ...sec7, pb(), ...appendix],
  }],
});

const out = path.join(__dirname, "QGlacierWatch_Project_Report.docx");
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(out, buf); console.log("wrote", out, buf.length, "bytes"); });
