"""Shared test setup."""
import pytest

from src import config


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path, monkeypatch):
    """Every test writes to its own audit database, never the real one."""
    monkeypatch.setattr(config, "AUDIT_DB", tmp_path / "audit.sqlite")
