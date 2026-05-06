from __future__ import annotations

from sqlite3 import Connection, Row

from cardforge.db.session import Database
from cardforge.domain.ids import validate_slug
from cardforge.files.asset_store import AssetStore
from cardforge.services.projects.project_scaffold import ProjectScaffold


class ProjectService:
    def __init__(self, db: Database | None = None, scaffold: ProjectScaffold | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.scaffold = scaffold or ProjectScaffold(self.asset_store)

    def create_project(self, slug: str, *, name: str = "", description: str = "") -> Row:
        slug = validate_slug(slug)
        root = self.scaffold.create(slug, name=name or slug)
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO projects(slug, name, description, root_path)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET name=excluded.name, description=excluded.description, updated_at=CURRENT_TIMESTAMP
                """,
                (slug, name or slug, description, str(root)),
            )
            return self.get_project(slug, conn=conn)

    def get_project(self, slug: str, *, conn: Connection | None = None) -> Row:
        slug = validate_slug(slug)
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            row = conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
            if row is None:
                raise KeyError(f"Project not found: {slug}")
            return row
        finally:
            if close:
                conn.close()

    def list_projects(self) -> list[Row]:
        with self.db.connection() as conn:
            return list(conn.execute("SELECT * FROM projects ORDER BY slug"))
