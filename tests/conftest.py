from __future__ import annotations

import os
from pathlib import Path

import pytest

from cardforge.db.schema import migrate
from cardforge.db.session import Database


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "workspace"
    monkeypatch.setenv("CARDFORGE_WORKSPACE", str(root))
    monkeypatch.setenv("CARDFORGE_DB_PATH", str(root / "cardforge.sqlite3"))
    return root


@pytest.fixture()
def db(workspace: Path) -> Database:
    database = Database()
    with database.connection() as conn:
        migrate(conn)
    return database
