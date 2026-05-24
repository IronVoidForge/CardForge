from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.sets.set_service import SetService


class PrintSheetExportService:
    """Export latest rendered card images as simple 3x3 print sheets."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.sets = SetService(self.db)

    def export_print_sheets(self, project_slug: str, set_code: str, *, side: str = "front") -> dict[str, Any]:
        side = "back" if side == "back" else "front"
        root = self.asset_store.project_root(project_slug)
        export_dir = root / "exports" / "print_sheets" / set_code.lower()
        export_dir.mkdir(parents=True, exist_ok=True)
        with self.db.connection() as conn:
            set_row = self.sets.get_set(project_slug, set_code, conn=conn)
            rows = conn.execute(
                """
                SELECT c.card_key, r.front_path, r.back_path
                FROM cards c
                LEFT JOIN renders r ON r.id = (
                    SELECT id FROM renders rr WHERE rr.card_id = c.id ORDER BY rr.created_at DESC, rr.id DESC LIMIT 1
                )
                WHERE c.set_id = ?
                ORDER BY c.card_key
                """,
                (set_row["id"],),
            ).fetchall()
        images: list[Image.Image] = []
        missing: list[str] = []
        for row in rows:
            rel = row["back_path"] if side == "back" else row["front_path"]
            if not rel:
                missing.append(row["card_key"])
                continue
            path = self.asset_store.safe_resolve(rel)
            if not path.exists():
                missing.append(row["card_key"])
                continue
            images.append(Image.open(path).convert("RGB"))
        sheet_paths: list[str] = []
        if images:
            card_w, card_h = images[0].size
            margin = 36
            gap = 18
            columns = 3
            rows_per_sheet = 3
            sheet_w = margin * 2 + columns * card_w + (columns - 1) * gap
            sheet_h = margin * 2 + rows_per_sheet * card_h + (rows_per_sheet - 1) * gap
            for offset in range(0, len(images), 9):
                sheet = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
                draw = ImageDraw.Draw(sheet)
                for slot, image in enumerate(images[offset : offset + 9]):
                    x = margin + (slot % columns) * (card_w + gap)
                    y = margin + (slot // columns) * (card_h + gap)
                    sheet.paste(image, (x, y))
                    draw.rectangle((x, y, x + card_w, y + card_h), outline=(180, 180, 180), width=2)
                out = export_dir / f"{set_code.lower()}_{side}_sheet_{offset // 9 + 1:02d}.png"
                sheet.save(out)
                sheet_paths.append(self.asset_store.relative_to_workspace(out))
        manifest = {"project_slug": project_slug, "set_code": set_code, "side": side, "sheet_paths": sheet_paths, "missing_render_cards": missing}
        self.asset_store.write_json(export_dir / f"{side}_PRINT_SHEET_MANIFEST.json", manifest)
        return manifest

    def export_game_package(self, project_slug: str) -> dict[str, Any]:
        root = self.asset_store.project_root(project_slug)
        out = root / "exports" / "game_package" / "magic_math_monsters_package"
        out.mkdir(parents=True, exist_ok=True)
        manifest = {"project_slug": project_slug, "output_path": self.asset_store.relative_to_workspace(out)}
        self.asset_store.write_json(out / "GAME_PACKAGE_MANIFEST.json", manifest)
        return manifest
