"""Pytest fixtures: every test runs against a throwaway SQLite DB and
audit log in a temp directory so tests never touch data/app.db or
data/audit.jsonl, and never call the real network / LLM."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import app.config as config


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "AUDIT_LOG_PATH", audit_path)

    # app.db / app.audit imported config values by name in some spots and
    # module reference in others -- patch both modules' bound names too.
    import app.db as db
    import app.audit as audit

    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(audit, "AUDIT_LOG_PATH", audit_path)

    db.init_db()
    yield
