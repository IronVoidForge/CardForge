from __future__ import annotations

import json
from sqlite3 import Connection, Row
from typing import Any

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.comfy.workflow_defaults import DEFAULT_COMFY_WORKFLOWS
from cardforge.services.comfy.workflow_patcher import WorkflowPatcher


class WorkflowRegistryService:
    """Global ComfyUI workflow registry backed by SQL and workspace JSON files."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.patcher = WorkflowPatcher()

    def sync_defaults(self) -> dict[str, Any]:
        workflow_root = self.db.settings.workspace_root / "workflows" / "comfy"
        workflow_root.mkdir(parents=True, exist_ok=True)
        synced: list[str] = []
        with self.db.connection() as conn:
            for workflow_key, definition in DEFAULT_COMFY_WORKFLOWS.items():
                workflow_path = workflow_root / str(definition["workflow_filename"])
                self.asset_store.write_json(workflow_path, definition["workflow_payload"])
                self._upsert(conn, workflow_key=workflow_key, name=str(definition["name"]), workflow_path=self.asset_store.relative_to_workspace(workflow_path), supported_job_type=str(definition["supported_job_type"]), patch_points=definition["patch_points"], default_settings=definition["default_settings"])
                synced.append(workflow_key)
        return {"synced_count": len(synced), "workflow_keys": synced}

    def list_workflows(self) -> list[dict[str, Any]]:
        self.sync_defaults()
        with self.db.connection() as conn:
            return [self._row_to_dict(row) for row in conn.execute("SELECT * FROM comfy_workflows ORDER BY workflow_key")]

    def get_workflow(self, workflow_key: str, *, conn: Connection | None = None) -> Row:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            if close:
                self.sync_defaults()
            row = conn.execute("SELECT * FROM comfy_workflows WHERE workflow_key = ?", (workflow_key,)).fetchone()
            if row is None:
                raise KeyError(f"Comfy workflow not found: {workflow_key}")
            return row
        finally:
            if close:
                conn.close()

    def load_workflow_payload(self, workflow_row: Row | dict[str, Any]) -> dict[str, Any]:
        raw_path = workflow_row["workflow_path"] if isinstance(workflow_row, Row) else workflow_row["workflow_path"]
        path = self.asset_store.safe_resolve(str(raw_path))
        if not path.exists():
            raise FileNotFoundError(f"Comfy workflow file not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Comfy workflow must be a JSON object: {path}")
        return payload

    def patch_points(self, workflow_row: Row | dict[str, Any]) -> dict[str, Any]:
        value = workflow_row["patch_points_json"] if isinstance(workflow_row, Row) else workflow_row.get("patch_points_json", "{}")
        return json.loads(value or "{}")

    def default_settings(self, workflow_row: Row | dict[str, Any]) -> dict[str, Any]:
        value = workflow_row["default_settings_json"] if isinstance(workflow_row, Row) else workflow_row.get("default_settings_json", "{}")
        return json.loads(value or "{}")

    def validate_workflow(self, workflow_key: str) -> dict[str, Any]:
        row = self.get_workflow(workflow_key)
        payload = self.load_workflow_payload(row)
        errors = self.patcher.validate_patch_points(payload, self.patch_points(row))
        return {"workflow_key": workflow_key, "valid": not errors, "errors": errors, "workflow_path": row["workflow_path"]}

    def _upsert(self, conn: Connection, *, workflow_key: str, name: str, workflow_path: str, supported_job_type: str, patch_points: dict[str, Any], default_settings: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO comfy_workflows(workflow_key, name, workflow_path, supported_job_type, patch_points_json, default_settings_json, enabled)
            VALUES(?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(workflow_key) DO UPDATE SET
              name=excluded.name,
              workflow_path=excluded.workflow_path,
              supported_job_type=excluded.supported_job_type,
              patch_points_json=excluded.patch_points_json,
              default_settings_json=excluded.default_settings_json,
              updated_at=CURRENT_TIMESTAMP
            """,
            (workflow_key, name, workflow_path, supported_job_type, json.dumps(patch_points, ensure_ascii=False), json.dumps(default_settings, ensure_ascii=False)),
        )

    def _row_to_dict(self, row: Row) -> dict[str, Any]:
        payload = {key: row[key] for key in row.keys()}
        for json_key in ("patch_points_json", "default_settings_json"):
            try:
                payload[json_key[:-5]] = json.loads(row[json_key] or "{}")
            except json.JSONDecodeError:
                payload[json_key[:-5]] = {}
        return payload
