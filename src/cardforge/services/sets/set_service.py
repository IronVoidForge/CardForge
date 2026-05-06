from __future__ import annotations

from sqlite3 import Connection, Row

from cardforge.db.session import Database
from cardforge.services.projects.project_service import ProjectService


class SetService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.projects = ProjectService(self.db)

    def create_set(self, project_slug: str, *, name: str, description: str = "", target_card_count: int = 0) -> Row:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            set_code = self._next_set_code(conn, project["id"])
            conn.execute(
                """
                INSERT INTO sets(project_id, set_code, name, description, target_card_count)
                VALUES(?, ?, ?, ?, ?)
                """,
                (project["id"], set_code, name, description, target_card_count),
            )
            return self.get_set(project_slug, set_code, conn=conn)

    def get_set(self, project_slug: str, set_code: str, *, conn: Connection | None = None) -> Row:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                "SELECT * FROM sets WHERE project_id = ? AND set_code = ?",
                (project["id"], set_code),
            ).fetchone()
            if row is None:
                raise KeyError(f"Set not found: {set_code}")
            return row
        finally:
            if close:
                conn.close()

    def list_sets(self, project_slug: str) -> list[Row]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            return list(conn.execute("SELECT * FROM sets WHERE project_id = ? ORDER BY set_code", (project["id"],)))


    def _next_set_code(self, conn: Connection, project_id: int) -> str:
        rows = conn.execute("SELECT set_code FROM sets WHERE project_id = ?", (project_id,)).fetchall()
        highest = 0
        for row in rows:
            value = str(row["set_code"])
            if value.startswith("SET") and value[3:].isdigit():
                highest = max(highest, int(value[3:]))
        return f"SET{highest + 1:03d}"
