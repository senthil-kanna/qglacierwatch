"""Headless render of every dashboard page against the real-mode artifacts, if they exist.

Skipped on a clean checkout (no processed data); CI runs it after the demo pipeline.
"""

from pathlib import Path

import pytest

from src import config

PAGES = sorted((config.ROOT / "dashboard" / "app_pages").glob("*.py"))


def _ready() -> bool:
    m = config.mode()
    return (config.processed_dir(m) / "latest.json").exists() and (config.artifact_dir(m) / "hindcasts.parquet").exists()


@pytest.mark.skipif(not _ready(), reason="no processed data/hindcasts for the current QGW_MODE")
@pytest.mark.parametrize("page", PAGES, ids=[p.stem for p in PAGES])
def test_page_renders_without_exception(page: Path):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(page), default_timeout=60).run()
    assert not at.exception, [e.message for e in at.exception]
