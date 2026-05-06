from __future__ import annotations

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.projects.project_service import ProjectService


def test_project_create_creates_db_and_folders(db: Database) -> None:
    project = ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    assert project["slug"] == "gravebound_test"
    root = AssetStore(db.settings).project_root("gravebound_test")
    assert root.exists()
    assert (root / "card_type_registry.json").exists()
    assert (root / "templates").exists()


def test_asset_store_rejects_path_escape(db: Database) -> None:
    store = AssetStore(db.settings)
    try:
        store.safe_resolve("../escape.txt")
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("Path escape was not rejected")
