from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from cardforge.db.schema import migrate
from cardforge.db.session import Database


def ensure_db() -> None:
    """Create or migrate the local SQLite database before command execution."""
    db = Database()
    with db.connection() as conn:
        migrate(conn)


def read_text_arg(inline: str, file_path: Path | None) -> str:
    if file_path is not None:
        return file_path.read_text(encoding="utf-8")
    return inline.strip()


def echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def parse_csv_tags(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
