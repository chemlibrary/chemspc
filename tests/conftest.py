"""Shared pytest fixtures for chemspc."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The application is a flat source bundle (main.py, db.py, gen1.py, ...), not a
# package installed under a separate src/ directory.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture
def db_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Return the database module configured to use an isolated SQLite file."""
    import db

    monkeypatch.setattr(db, "DATABASE_NAME", str(tmp_path / "chemspc-test.db"))
    return db
