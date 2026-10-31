"""Optional S3 mirror of the three storage roots (QGW_DATA, QGW_ARTIFACTS, QGW_REPORTS).

All code reads and writes the local filesystem. In AWS, containers pull what they need from the
bucket at start and jobs push what they changed when they finish. Without QGW_S3_BUCKET every call
is a no-op, so local development is unchanged.

A "part" is a directory or file path relative to the roots: its first segment names the root and
it becomes the S3 key prefix, e.g. "data/raw", "artifacts/real", "artifacts/real/hindcasts.parquet".

Usage:
    python -m src.storage pull data/raw data/processed/real artifacts/real reports/real
    python -m src.storage push reports/real
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

from src import config

ROOT_ENV = {"data": "QGW_DATA", "artifacts": "QGW_ARTIFACTS", "reports": "QGW_REPORTS"}
# Objects stay single-part below this size, so their ETag is the MD5 and change detection is exact.
SINGLE_PART_LIMIT = 256 * 1024 * 1024


def bucket() -> str | None:
    return os.getenv("QGW_S3_BUCKET") or None


def root_of(name: str) -> Path:
    if name == "data":
        return config.data_root()
    if name == "artifacts":
        return config.artifact_dir("real").parent
    if name == "reports":
        return config.reports_dir("real").parent
    raise ValueError(f"unknown storage root {name!r}; one of {sorted(ROOT_ENV)}")


def _split(part: str) -> tuple[str, str]:
    part = part.strip("/")
    name, _, rest = part.partition("/")
    if name not in ROOT_ENV or ".." in Path(part).parts:
        raise ValueError(f"bad part {part!r}; must start with one of {sorted(ROOT_ENV)}")
    return name, rest


def local_dir(part: str) -> Path:
    name, rest = _split(part)
    return root_of(name) / rest if rest else root_of(name)


def _client():
    import boto3

    return boto3.client("s3")


def _md5(path: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _same(path: Path, size: int, etag: str) -> bool:
    if not path.exists() or path.stat().st_size != size:
        return False
    etag = etag.strip('"')
    return "-" in etag or _md5(path) == etag  # multipart ETag is not an MD5; size match is all we have


def _objects(s3, b: str, prefix: str):
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=prefix):
        yield from page.get("Contents", [])


def pull(parts: list[str], dest_root: Path | None = None) -> int:
    """Download each part's objects that are missing or differ locally. Returns files downloaded."""
    b = bucket()
    if not b:
        print("QGW_S3_BUCKET not set; using the local filesystem only", flush=True)
        return 0
    s3, n = _client(), 0
    for part in parts:
        name, rest = _split(part)
        key0 = part.strip("/")
        base = (dest_root / name if dest_root else root_of(name)) / rest
        for obj in _objects(s3, b, key0):
            key = obj["Key"]
            if key == key0:  # the part is a single file
                target = base
            elif key.startswith(key0 + "/") and not key.endswith("/"):
                target = base / key[len(key0) + 1:]
            else:
                continue
            if _same(target, obj["Size"], obj["ETag"]):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(b, obj["Key"], str(target))
            n += 1
    print(f"pulled {n} file(s) from s3://{b} for {parts}", flush=True)
    return n


def snapshot(parts: list[str]) -> dict[str, tuple[int, int]]:
    """(size, mtime_ns) of every local file in the parts, to push only what a job changed."""
    out = {}
    for part in parts:
        d = local_dir(part)
        for p in [d] if d.is_file() else d.rglob("*") if d.exists() else []:
            if p.is_file():
                st = p.stat()
                out[str(p)] = (st.st_size, st.st_mtime_ns)
    return out


def push(parts: list[str], since: dict[str, tuple[int, int]] | None = None) -> int:
    """Upload new or changed files (all files when `since` is None). Never deletes remote objects."""
    b = bucket()
    if not b:
        print("QGW_S3_BUCKET not set; nothing pushed", flush=True)
        return 0
    from boto3.s3.transfer import TransferConfig

    tc = TransferConfig(multipart_threshold=SINGLE_PART_LIMIT)
    s3, n = _client(), 0
    now = snapshot(parts)
    for part in parts:
        base = local_dir(part)
        for path, sig in now.items():
            p = Path(path)
            if not p.is_relative_to(base) or (since is not None and since.get(path) == sig):
                continue
            key = part.strip("/") if p == base else f"{part.strip('/')}/{p.relative_to(base).as_posix()}"
            s3.upload_file(str(p), b, key, Config=tc)
            n += 1
    print(f"pushed {n} file(s) to s3://{b} for {parts}", flush=True)
    return n


def hydrate(parts: list[str], dest_root: Path) -> list[str]:
    """Pull parts into dest_root and point each fully pulled root's env var at it.

    Used where the image is read-only and already carries a baked copy (the API Lambda): a root is
    switched to the fresh copy only if every part under it downloaded, otherwise the baked copy
    keeps serving. Returns the roots that were switched."""
    if not bucket():
        return []
    switched = []
    by_root: dict[str, list[str]] = {}
    for part in parts:
        by_root.setdefault(_split(part)[0], []).append(part)
    for name, ps in by_root.items():
        try:
            pull(ps, dest_root)
        except Exception as e:  # any S3 failure falls back to the baked copy
            print(f"warning: could not pull {ps} ({e}); serving the copy baked into the image", file=sys.stderr, flush=True)
            continue
        if all((dest_root / p.strip("/")).exists() for p in ps):
            os.environ[ROOT_ENV[name]] = str(dest_root / name)
            switched.append(name)
    return switched


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["pull", "push"])
    p.add_argument("parts", nargs="+")
    args = p.parse_args()
    (pull if args.command == "pull" else push)(args.parts)


if __name__ == "__main__":
    main()
