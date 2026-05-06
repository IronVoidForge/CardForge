from __future__ import annotations

from sqlite3 import Connection

from cardforge.db.table_definitions import SCHEMA_SQL, SCHEMA_VERSION


def migrate(conn: Connection) -> None:
    for sql in SCHEMA_SQL:
        conn.execute(sql)
    _ensure_generation_jobs_updated_at(conn)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )


def reset(conn: Connection) -> None:
    tables = [
        "lab_promotion_requests", "image_lab_attempts", "image_lab_cases", "prompt_lab_runs", "prompt_lab_cases",
        "audit_events", "exports", "auto_reviews", "rework_requests", "review_decisions", "review_items", "renders", "templates",
        "art_candidates", "art_prompts", "comfy_jobs", "comfy_workflows", "generation_jobs", "prompt_packages", "prompt_template_versions", "prompt_templates", "llm_requests",
        "card_versions", "cards", "card_batches", "factions", "keywords", "card_types", "set_briefs", "sets",
        "projects", "schema_meta",
    ]
    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    migrate(conn)


def _ensure_generation_jobs_updated_at(conn: Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(generation_jobs)").fetchall()}
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE generation_jobs ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
