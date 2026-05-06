from __future__ import annotations

import json
from sqlite3 import Connection
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore


class LLMRequestLog:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)

    def create(
        self,
        conn: Connection,
        *,
        project_id: int,
        set_id: int | None,
        card_id: int | None,
        batch_id: int | None,
        project_slug: str,
        task_type: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> int:
        conn.execute(
            """
            INSERT INTO llm_requests(project_id, set_id, card_id, batch_id, task_type, model, temperature, max_tokens, status)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'planned')
            """,
            (project_id, set_id, card_id, batch_id, task_type, model, temperature, max_tokens),
        )
        request_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        root = self.asset_store.project_root(project_slug) / "logs" / "llm" / f"LLM_{request_id:04d}"
        system_path = root / "system_prompt.md"
        user_path = root / "user_prompt.md"
        self.asset_store.write_text(system_path, system_prompt)
        self.asset_store.write_text(user_path, user_prompt)
        conn.execute(
            """
            UPDATE llm_requests
            SET system_prompt_path = ?, user_prompt_path = ?, status = 'running'
            WHERE id = ?
            """,
            (
                self.asset_store.relative_to_workspace(system_path),
                self.asset_store.relative_to_workspace(user_path),
                request_id,
            ),
        )
        return request_id

    def complete(
        self,
        conn: Connection,
        *,
        request_id: int,
        project_slug: str,
        raw_response: str,
        parsed_payload: Any,
    ) -> None:
        root = self.asset_store.project_root(project_slug) / "logs" / "llm" / f"LLM_{request_id:04d}"
        raw_path = root / "raw_response.md"
        self.asset_store.write_text(raw_path, raw_response)
        conn.execute(
            """
            UPDATE llm_requests
            SET raw_response_path = ?, parsed_response_json = ?, status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                self.asset_store.relative_to_workspace(raw_path),
                json.dumps(parsed_payload, ensure_ascii=False),
                request_id,
            ),
        )

    def fail(self, conn: Connection, *, request_id: int, error: str) -> None:
        conn.execute(
            """
            UPDATE llm_requests
            SET status = 'failed', error_message = ?, completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error, request_id),
        )
