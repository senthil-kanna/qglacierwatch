"""S3 mirror (src.storage) against an in-memory fake client: no AWS access needed."""

import hashlib
import os

import pytest

from src import storage


class FakeS3:
    def __init__(self, fail=False):
        self.objects: dict[str, bytes] = {}
        self.uploads: list[str] = []
        self.fail = fail

    def get_paginator(self, _name):
        fake = self

        class Pager:
            def paginate(self, Bucket, Prefix):
                if fake.fail:
                    raise ConnectionError("no network")
                yield {"Contents": [{"Key": k, "Size": len(v), "ETag": f'"{hashlib.md5(v).hexdigest()}"'}
                                    for k, v in sorted(fake.objects.items()) if k.startswith(Prefix)]}

        return Pager()

    def download_file(self, _bucket, key, filename):
        with open(filename, "wb") as fh:
            fh.write(self.objects[key])

    def upload_file(self, filename, _bucket, key, Config=None):
        with open(filename, "rb") as fh:
            self.objects[key] = fh.read()
        self.uploads.append(key)


@pytest.fixture
def roots(tmp_path, monkeypatch):
    for name, env in storage.ROOT_ENV.items():
        monkeypatch.setenv(env, str(tmp_path / "local" / name))
    return tmp_path


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    monkeypatch.setenv("QGW_S3_BUCKET", "qgw-test")
    return fake


def test_no_bucket_is_a_noop(roots, monkeypatch):
    monkeypatch.delenv("QGW_S3_BUCKET", raising=False)
    monkeypatch.setattr(storage, "_client", lambda: pytest.fail("must not touch S3"))
    assert storage.pull(["reports/real"]) == 0
    assert storage.push(["reports/real"]) == 0
    assert storage.hydrate(["reports/real"], roots / "tmp") == []


def test_part_maps_to_root_and_rejects_bad_paths(roots):
    assert storage.local_dir("data/processed/real") == roots / "local" / "data" / "processed" / "real"
    assert storage.local_dir("artifacts/real") == roots / "local" / "artifacts" / "real"
    for bad in ["external/x", "data/../secrets", "../data"]:
        with pytest.raises(ValueError):
            storage.local_dir(bad)


def test_pull_downloads_only_missing_or_changed(roots, s3):
    s3.objects = {"reports/real/a.json": b"{}", "reports/real/sub/b.json": b"[1]", "reports/demo/c.json": b"x"}
    assert storage.pull(["reports/real"]) == 2
    assert (roots / "local" / "reports" / "real" / "sub" / "b.json").read_bytes() == b"[1]"
    assert not (roots / "local" / "reports" / "demo").exists()
    assert storage.pull(["reports/real"]) == 0
    s3.objects["reports/real/a.json"] = b'{"v": 2}'
    assert storage.pull(["reports/real"]) == 1


def test_push_uploads_only_what_changed_since_snapshot(roots, s3):
    d = roots / "local" / "reports" / "real"
    d.mkdir(parents=True)
    (d / "keep.json").write_text("1")
    (d / "drift_latest.json").write_text("old")
    before = storage.snapshot(["reports/real"])
    (d / "drift_latest.json").write_text("new value")
    (d / "added.json").write_text("2")
    assert storage.push(["reports/real"], since=before) == 2
    assert sorted(s3.uploads) == ["reports/real/added.json", "reports/real/drift_latest.json"]
    assert storage.push(["reports/real"]) == 3


def test_hydrate_switches_root_only_when_pull_succeeds(roots, s3, monkeypatch):
    s3.objects = {"reports/real/drift_latest.json": b"{}"}
    baked = os.environ["QGW_DATA"]
    switched = storage.hydrate(["reports/real", "data/processed/real"], roots / "tmp")
    assert switched == ["reports"]  # nothing under data/processed/real in S3, so data stays baked
    assert os.environ["QGW_REPORTS"] == str(roots / "tmp" / "reports")
    assert os.environ["QGW_DATA"] == baked
    s3.fail = True
    monkeypatch.setenv("QGW_REPORTS", "baked")
    assert storage.hydrate(["reports/real"], roots / "tmp2") == []
    assert os.environ["QGW_REPORTS"] == "baked"
