from __future__ import annotations

import re
from sqlite3 import Connection

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,80}$")


def validate_slug(slug: str) -> str:
    value = str(slug or "").strip().lower()
    if not SLUG_PATTERN.fullmatch(value):
        raise ValueError("Slug must be lowercase letters, numbers, dashes, or underscores, 2-81 chars.")
    return value


def slugify(value: str, *, fallback: str = "item") -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return text or fallback


def next_key(conn: Connection, table: str, column: str, prefix: str, *, width: int = 4, where: str = "", params: tuple = ()) -> str:
    sql = f"SELECT {column} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    rows = conn.execute(sql, params).fetchall()
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    for row in rows:
        match = pattern.fullmatch(str(row[column]))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}_{highest + 1:0{width}d}"
