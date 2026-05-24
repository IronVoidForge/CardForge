from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from cardforge.db.session import Database
from cardforge.files.asset_store import AssetStore
from cardforge.services.projects.project_service import ProjectService


class WorksheetService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)

    def import_worksheets(self, project_slug: str, worksheet_json: Path, *, replace_existing: bool = False) -> dict[str, Any]:
        self.projects.get_project(project_slug)
        payload = json.loads(Path(worksheet_json).read_text(encoding="utf-8"))
        items = self._items(payload)
        root = self.asset_store.project_root(project_slug) / "worksheets"
        json_dir = root / "json"
        if replace_existing and json_dir.exists():
            for path in json_dir.glob("*.json"):
                path.unlink()
        json_dir.mkdir(parents=True, exist_ok=True)
        for index, item in enumerate(items, 1):
            wid = str(item.get("id") or item.get("worksheet_id") or f"WS-{index:03d}")
            self.asset_store.write_json(json_dir / f"{wid}.json", item)
        manifest = {"project_slug": project_slug, "worksheet_count": len(items), "source_path": str(worksheet_json)}
        self.asset_store.write_json(root / "WORKSHEET_MANIFEST.json", manifest)
        return manifest

    def render_worksheets(self, project_slug: str, *, low_ink: bool = True) -> dict[str, Any]:
        self.projects.get_project(project_slug)
        root = self.asset_store.project_root(project_slug) / "worksheets"
        json_dir = root / "json"
        render_dir = root / "renders"
        render_dir.mkdir(parents=True, exist_ok=True)
        rendered: list[str] = []
        answers: list[str] = ["# Worksheet Answer Key", ""]
        for path in sorted(json_dir.glob("*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            wid = str(item.get("id") or path.stem)
            title = str(item.get("title") or wid)
            instructions = item.get("printed_instructions") or item.get("instructions") or []
            if isinstance(instructions, str):
                instructions = [instructions]
            problems = item.get("problems") or item.get("answer_key") or []
            image = Image.new("RGB", (1700, 2200), (255, 255, 255))
            draw = ImageDraw.Draw(image)
            y = 80
            draw.text((90, y), title, fill=(20, 20, 20))
            y += 80
            draw.text((90, y), wid, fill=(90, 90, 90))
            y += 80
            for line in instructions[:6]:
                draw.text((90, y), f"- {line}", fill=(20, 20, 20))
                y += 55
            y += 40
            if problems:
                for number, problem in enumerate(problems[:10], 1):
                    if isinstance(problem, dict):
                        text = str(problem.get("problem") or problem.get("prompt") or "Solve the puzzle.")
                        answer = str(problem.get("answer") or "")
                    else:
                        text = str(problem)
                        answer = ""
                    draw.text((110, y), f"{number}. {text}", fill=(30, 30, 30))
                    draw.line((180, y + 50, 1500, y + 50), fill=(120, 120, 120), width=2)
                    y += 120
                    if answer:
                        answers.append(f"- **{wid} #{number}:** {answer}")
            else:
                for number in range(1, 7):
                    draw.text((110, y), f"{number}. ________________________________", fill=(30, 30, 30))
                    y += 120
            out = render_dir / f"{wid}.png"
            image.save(out)
            rendered.append(self.asset_store.relative_to_workspace(out))
        answer_key = root / "answer_key.md"
        self.asset_store.write_text(answer_key, "\n".join(answers) + "\n")
        return {"project_slug": project_slug, "rendered_count": len(rendered), "rendered_paths": rendered, "answer_key_path": self.asset_store.relative_to_workspace(answer_key)}

    def export_worksheets(self, project_slug: str) -> dict[str, Any]:
        root = self.asset_store.project_root(project_slug) / "worksheets"
        render_dir = root / "renders"
        paths = [self.asset_store.relative_to_workspace(path) for path in sorted(render_dir.glob("*.png"))]
        return {"project_slug": project_slug, "worksheet_count": len(paths), "rendered_paths": paths, "answer_key_path": self.asset_store.relative_to_workspace(root / "answer_key.md")}

    def _items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("worksheets", "worksheet_pages", "pages"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [payload]
        return []
