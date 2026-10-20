"""Scheduled refresh job: staged ingest -> manifest check -> features -> drift check.

Ingest runs into a staging data root. Staged files are compared byte-for-byte (SHA-256) with the
recorded raw manifest: new files are added, identical files are kept, and any file whose bytes
changed stops the job, because overwriting raw inputs would silently change the data current
models were trained on. Extending the record means a new data version and a retrain.

Usage:
    python -m src.pipeline.refresh                # real mode, needs Earth Engine credentials
    python -m src.pipeline.refresh --skip-ingest  # rebuild features + drift from existing raw data
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

from src import config
from src.ingest.provenance import MANIFEST, record_or_verify, sha256


def step(*args: str, env: dict | None = None) -> None:
    print(f"$ python -m {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, "-m", *args], check=True, env=env)


def stage_and_merge(raw, staging) -> dict:
    manifest = json.loads((raw / MANIFEST).read_text())["files"] if (raw / MANIFEST).exists() else {}
    changed, added, same = [], [], []
    for p in sorted(staging.iterdir()):
        if not p.is_file():
            continue
        rec = manifest.get(p.name)
        if rec is None:
            shutil.copy2(p, raw / p.name)
            added.append(p.name)
        elif rec["sha256"] == sha256(p):
            same.append(p.name)
        else:
            changed.append(p.name)
    return {"added": added, "unchanged": same, "changed": changed}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-ingest", action="store_true")
    args = p.parse_args()
    raw = config.raw_dir("real")
    raw.mkdir(parents=True, exist_ok=True)
    if not args.skip_ingest:
        stage_root = config.data_root() / "staging"
        env = {**os.environ, "QGW_DATA": str(stage_root)}
        step("src.ingest.earth_engine", env=env)
        step("src.ingest.discharge", env=env)
        merge = stage_and_merge(raw, stage_root / "raw")
        print(json.dumps(merge, indent=2))
        if merge["changed"]:
            raise SystemExit(f"Staged files differ from recorded raw data: {merge['changed']}. Not overwriting; create a new data version.")
    print(json.dumps(record_or_verify(raw), indent=2))
    step("src.features.build", "--mode", "real")
    step("src.drift.replay", "--mode", "real", "--latest")


if __name__ == "__main__":
    main()
