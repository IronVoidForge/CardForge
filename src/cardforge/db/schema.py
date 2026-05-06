from __future__ import annotations

from sqlite3 import Connection

from cardforge.db.table_definitions import SCHEMA_SQL, SCHEMA_VERSION


def migrate(conn: Connection) -> None:
    for sql in SCHEMA_SQL:
        conn.execute(sql)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )


def reset(conn: Connection) -> None:
    tables = [
        "audit_events", "exports", "auto_reviews", "rework_requests", "review_decisions", "review_items", "renders", "templates",
        "art_candidates", "art_prompts", "comfy_jobs", "comfy_workflows", "generation_jobs", "prompt_packages", "prompt_templates", "llm_requests",
        "card_versions", "cards", "card_batches", "factions", "keywords", "card_types", "set_briefs", "sets",
        "projects", "schema_meta",
    ]
    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    migrate(conn)
