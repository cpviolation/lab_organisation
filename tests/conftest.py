from pathlib import Path

import pytest

from labcourse import db
from labcourse.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fx() -> Path:
    return FIXTURES


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(root=tmp_path, title="Laboratorio I", database=tmp_path / "lab.db",
                  output_dir=tmp_path / "out", backup_dir=tmp_path / "bk", default_cohort="2025/26")


@pytest.fixture
def conn(cfg):
    c = db.connect(cfg.database)
    yield c
    c.close()


def run(conn, fn, *args, dry_run=False, **kwargs):
    with db.transaction(conn, dry_run=dry_run):
        return fn(conn, *args, **kwargs)
