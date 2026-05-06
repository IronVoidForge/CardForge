from __future__ import annotations

from pathlib import Path
from typing import Any

from cardforge.db.schema import migrate
from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore


class DiagnosticsService:
    """Cheap local health checks that do not require live LM Studio or ComfyUI."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)

    def check(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        checks.append(self._workspace_check())
        checks.append(self._database_check())
        checks.append(self._integration_config_check("lmstudio", self.db.settings.lmstudio_base_url))
        checks.append(self._integration_config_check("comfyui", self.db.settings.comfy_base_url))
        return {
            "ok": all(item["ok"] for item in checks),
            "checks": checks,
            "workspace_root": str(self.db.settings.workspace_root),
            "database_path": str(self.db.settings.database_path),
        }

    def _workspace_check(self) -> dict[str, Any]:
        try:
            root = self.asset_store.ensure_workspace()
            probe = root / ".cardforge_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return {"name": "workspace_writable", "ok": True, "detail": str(root)}
        except Exception as exc:
            return {"name": "workspace_writable", "ok": False, "detail": str(exc)}

    def _database_check(self) -> dict[str, Any]:
        try:
            with self.db.connection() as conn:
                migrate(conn)
                conn.execute("SELECT 1").fetchone()
            return {"name": "database", "ok": True, "detail": str(self.db.path)}
        except Exception as exc:
            return {"name": "database", "ok": False, "detail": str(exc)}

    def _integration_config_check(self, name: str, base_url: str) -> dict[str, Any]:
        detail = base_url.strip()
        return {"name": f"{name}_configured", "ok": bool(detail), "detail": detail or "missing base URL"}

    def project_storage_summary(self, project_root: Path) -> dict[str, Any]:
        file_count = 0
        total_bytes = 0
        if project_root.exists():
            for path in project_root.rglob("*"):
                if path.is_file():
                    file_count += 1
                    total_bytes += path.stat().st_size
        return {"file_count": file_count, "total_bytes": total_bytes}
