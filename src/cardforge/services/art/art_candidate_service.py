from __future__ import annotations

import json
import random
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from cardforge.db.session import Database
from cardforge.domain.ids import next_key
from cardforge.files.asset_store import AssetStore
from cardforge.services.art.art_prompt_service import ArtPromptService
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.review.review_service import ReviewService


class ArtCandidateService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.cards = CardService(self.db)
        self.projects = ProjectService(self.db)
        self.prompts = ArtPromptService(self.db)

    def generate_dummy_candidates(self, project_slug: str, card_key: str, *, count: int = 4, seed: int | None = None) -> dict[str, Any]:
        count = max(1, min(12, int(count)))
        rng = random.Random(seed if seed is not None else 1000)
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            prompt = conn.execute("SELECT * FROM art_prompts WHERE card_id = ? ORDER BY version_number DESC LIMIT 1", (card["id"],)).fetchone()
            if prompt is None:
                created = self.prompts.create_prompt(project_slug, card_key)
                prompt = conn.execute("SELECT * FROM art_prompts WHERE id = ?", (created["art_prompt_id"],)).fetchone()
            art_dir = self.asset_store.project_root(project_slug) / "cards" / card_key / "art" / "candidates"
            art_dir.mkdir(parents=True, exist_ok=True)
            created_keys: list[str] = []
            for _ in range(count):
                candidate_key = next_key(conn, "art_candidates", "candidate_key", "ART_CAND", where="card_id = ?", params=(card["id"],))
                image_path = art_dir / f"{candidate_key}.png"
                thumb_path = art_dir / f"{candidate_key}_thumb.png"
                self._draw_dummy_art(card["name"], image_path, rng=rng)
                Image.open(image_path).resize((256, 192)).save(thumb_path)
                conn.execute(
                    """
                    INSERT INTO art_candidates(card_id, art_prompt_id, candidate_key, image_path, thumbnail_path, seed, workflow_key, settings_json, status, review_status)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        card["id"], prompt["id"], candidate_key,
                        self.asset_store.relative_to_workspace(image_path),
                        self.asset_store.relative_to_workspace(thumb_path),
                        rng.randint(1, 999999),
                        "offline_dummy_art_v1",
                        json.dumps({"offline_dummy": True, "width": 1024, "height": 768}),
                        "generated",
                        "open",
                    ),
                )
                created_keys.append(candidate_key)
            ReviewService(self.db).enqueue(
                project_id=project["id"],
                set_id=card["set_id"],
                target_type="card_art",
                target_id=card_key,
                review_type="art_candidate",
                title=f"Review art candidates: {card['name']}",
                description=f"{count} offline dummy art candidate(s) generated.",
                metadata={"candidate_keys": created_keys, "offline_dummy": True},
                conn=conn,
            )
            return {"card_key": card_key, "created_count": len(created_keys), "candidate_keys": created_keys}

    def list_candidates(self, project_slug: str, card_key: str) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            rows = conn.execute("SELECT * FROM art_candidates WHERE card_id = ? ORDER BY candidate_key", (card["id"],)).fetchall()
            return [{key: row[key] for key in row.keys()} for row in rows]

    def approve(self, project_slug: str, candidate_key: str) -> dict[str, Any]:
        return self._update_status(project_slug, candidate_key, status="approved", review_status="approved")

    def reject(self, project_slug: str, candidate_key: str, *, reason: str = "") -> dict[str, Any]:
        result = self._update_status(project_slug, candidate_key, status="rejected", review_status="rejected")
        result["reason"] = reason
        return result

    def lock(self, project_slug: str, candidate_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                """
                SELECT ac.*, c.card_key FROM art_candidates ac
                JOIN cards c ON c.id = ac.card_id
                JOIN sets s ON s.id = c.set_id
                WHERE s.project_id = ? AND ac.candidate_key = ?
                """,
                (project["id"], candidate_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"Art candidate not found: {candidate_key}")
            conn.execute("UPDATE art_candidates SET status = 'approved', review_status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE card_id = ? AND status = 'locked'", (row["card_id"],))
            conn.execute("UPDATE art_candidates SET status = 'locked', review_status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
            source = self.asset_store.safe_resolve(row["image_path"])
            locked_path = self.asset_store.project_root(project_slug) / "cards" / row["card_key"] / "art" / "locked_art.png"
            locked_path.parent.mkdir(parents=True, exist_ok=True)
            Image.open(source).save(locked_path)
            return {"candidate_key": candidate_key, "card_key": row["card_key"], "locked_art_path": self.asset_store.relative_to_workspace(locked_path)}

    def _update_status(self, project_slug: str, candidate_key: str, *, status: str, review_status: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute(
                """
                SELECT ac.*, c.card_key FROM art_candidates ac
                JOIN cards c ON c.id = ac.card_id
                JOIN sets s ON s.id = c.set_id
                WHERE s.project_id = ? AND ac.candidate_key = ?
                """,
                (project["id"], candidate_key),
            ).fetchone()
            if row is None:
                raise KeyError(f"Art candidate not found: {candidate_key}")
            conn.execute("UPDATE art_candidates SET status = ?, review_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, review_status, row["id"]))
            return {"candidate_key": candidate_key, "card_key": row["card_key"], "status": status, "review_status": review_status}

    def _draw_dummy_art(self, title: str, path, *, rng: random.Random) -> None:
        width, height = 1024, 768
        base = (rng.randint(55, 110), rng.randint(45, 85), rng.randint(80, 145))
        accent = (rng.randint(160, 230), rng.randint(130, 190), rng.randint(80, 140))
        img = Image.new("RGB", (width, height), base)
        draw = ImageDraw.Draw(img)
        for i in range(18):
            x0 = rng.randint(-100, width)
            y0 = rng.randint(-100, height)
            x1 = x0 + rng.randint(120, 420)
            y1 = y0 + rng.randint(80, 300)
            color = tuple(max(0, min(255, c + rng.randint(-45, 45))) for c in accent)
            draw.ellipse((x0, y0, x1, y1), outline=color, width=rng.randint(2, 8))
        draw.rectangle((0, int(height * 0.65), width, height), fill=(35, 30, 42))
        draw.ellipse((370, 130, 650, 560), fill=(215, 205, 180), outline=(45, 35, 55), width=10)
        draw.rectangle((490, 420, 530, 650), fill=(80, 65, 75))
        draw.ellipse((468, 80, 552, 175), fill=(225, 195, 110))
        self._center_text(draw, title[:34], (70, 660, 954, 735), fill=(235, 225, 190))
        img.save(path)

    def _center_text(self, draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int], *, fill: tuple[int, int, int]) -> None:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 42)
        except OSError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        x = box[0] + ((box[2] - box[0]) - (bbox[2] - bbox[0])) // 2
        y = box[1] + ((box[3] - box[1]) - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), text, font=font, fill=fill)

# Backward-compatible method names used by tests and early CLI sketches.
def _art_candidate_locked_art_path(self, project_slug: str, card_key: str):
    path = self.asset_store.project_root(project_slug) / "cards" / card_key / "art" / "locked_art.png"
    return path if path.exists() else None


def _art_candidate_approve_candidate(self, project_slug: str, candidate_key: str):
    return self.approve(project_slug, candidate_key)


def _art_candidate_lock_candidate(self, project_slug: str, candidate_key: str):
    return self.lock(project_slug, candidate_key)


ArtCandidateService.locked_art_path = _art_candidate_locked_art_path
ArtCandidateService.approve_candidate = _art_candidate_approve_candidate
ArtCandidateService.lock_candidate = _art_candidate_lock_candidate
