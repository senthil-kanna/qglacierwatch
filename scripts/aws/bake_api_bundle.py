"""Copy what the API serves into build/api-bundle/ for docker/Dockerfile.api (AWS Lambda).

Only the serving model is copied (production if promoted, else the newest candidate), not the
whole registry, so the image stays small and cold starts read nothing from S3 except the
optional report/feature refresh (QGW_S3_PULL). Reads the normal roots (QGW_DATA, QGW_ARTIFACTS,
QGW_REPORTS); in CI they are filled first with `python -m src.storage pull ...`.

Usage:
    python scripts/aws/bake_api_bundle.py [--out build/api-bundle] [--mode real]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import config  # noqa: E402
from src.serving.store import Store  # noqa: E402


def bake(out: Path, mode: str) -> dict:
    model_id, status = Store(mode).serving_model()
    if model_id is None:
        raise SystemExit(f"No registered model under {config.artifact_dir(mode)}; run training or `src.storage pull artifacts/{mode}` first.")
    if out.exists():
        shutil.rmtree(out)
    art, reg = config.artifact_dir(mode), config.artifact_dir(mode) / "registry"
    copies = {
        reg / "registry.json": out / "artifacts" / mode / "registry" / "registry.json",
        reg / "models" / model_id: out / "artifacts" / mode / "registry" / "models" / model_id,
        art / "hindcasts.parquet": out / "artifacts" / mode / "hindcasts.parquet",
        config.processed_dir(mode): out / "data" / "processed" / mode,
        config.reports_dir(mode): out / "reports" / mode,
    }
    for src, dst in copies.items():
        if not src.exists():
            if src.name == "hindcasts.parquet":
                continue  # optional: /v1/hindcast answers 503 without it
            raise SystemExit(f"missing {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.log", "*.md"))
        else:
            shutil.copy2(src, dst)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    info = {"mode": mode, "model_id": model_id, "model_status": status, "bytes": size}
    (out / "BUNDLE.json").write_text(json.dumps(info, indent=2))
    return info


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(config.ROOT / "build" / "api-bundle"))
    p.add_argument("--mode", default="real", choices=config.MODES)
    args = p.parse_args()
    info = bake(Path(args.out), args.mode)
    print(f"baked {info['model_id']} ({info['model_status']}), {info['bytes'] / 1e6:.1f} MB -> {args.out}")


if __name__ == "__main__":
    main()
