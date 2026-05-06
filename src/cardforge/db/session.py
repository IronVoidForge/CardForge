from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cardforge.config import AppSettings, load_settings


class Database:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or load_settings()
        self.path = self.settings.database_path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def database_from_path(path: Path) -> Database:
    settings = load_settings()
    return Database(settings=AppSettings(**{**settings.__dict__, "database_path": path}))
