from __future__ import annotations

import json
import random
from pathlib import Path
from sqlite3 import Connection, Row
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from cardforge.db.session import Database
from cardforge.domain.ids import next_key
from cardforge.files.asset_store import AssetStore
from cardforge.services.art.art_prompt_service import ArtPromptService
from cardforge.services.cards.card_service import CardService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.review.review_service import ReviewService

IMAGE_LAB_DECISIONS = {"accepted", "rejected", "maybe", "needs_rework", "unreviewed"}


class ImageLabService:
    """Offline-safe image prompt workbench for card art direction.

    Image Lab attempts write only to ``99_image_lab``.  They help narrow down art
    prompt families before production ComfyUI jobs are prepared or submitted.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.cards = CardService(self.db)
        self.art_prompts = ArtPromptService(self.db)

    def create_case(self, project_slug: str, card_key: str, *, notes: str = "") -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            prompt = conn.execute("SELECT * FROM art_prompts WHERE card_id = ? ORDER BY version_number DESC LIMIT 1", (card["id"],)).fetchone()
            if prompt is None:
                created = self.art_prompts.create_prompt(project_slug, card_key)
                prompt = conn.execute("SELECT * FROM art_prompts WHERE id = ?", (created["art_prompt_id"],)).fetchone()
            case_key = next_key(conn, "image_lab_cases", "case_key", "ILAB", where="project_id = ?", params=(project["id"],))
            case_dir = self.asset_store.project_root(project_slug) / "99_image_lab" / "cases" / case_key
            snapshot = self._card_snapshot(card, prompt)
            manifest = {
                "case_key": case_key,
                "project_slug": project_slug,
                "mode": "card_art",
                "target_type": "card",
                "target_id": card_key,
                "card_name": card["name"],
                "production_artifacts_read_only": True,
                "writes_production_artifacts": False,
                "notes": notes,
            }
            self.asset_store.write_json(case_dir / "case_manifest.json", manifest)
            self.asset_store.write_json(case_dir / "input_snapshot.json", snapshot)
            self.asset_store.write_text(case_dir / "workback_notes.md", _workback_notes(card, prompt, notes))
            conn.execute(
                """
                INSERT INTO image_lab_cases(project_id, card_id, case_key, mode, target_type, target_id, case_dir, notes)
                VALUES(?, ?, ?, 'card_art', 'card', ?, ?, ?)
                """,
                (project["id"], card["id"], case_key, card_key, self.asset_store.relative_to_workspace(case_dir), notes),
            )
            ReviewService(self.db).enqueue(
                project_id=project["id"],
                set_id=card["set_id"],
                target_type="image_lab_case",
                target_id=case_key,
                review_type="image_lab",
                title=f"Image Lab case {case_key}: {card['name']}",
                description="Run isolated art prompt attempts and promote only the best prompt lessons.",
                metadata=manifest,
                conn=conn,
            )
            return {**manifest, "case_dir": self.asset_store.relative_to_workspace(case_dir)}

    def list_cases(self, project_slug: str) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            rows = conn.execute("SELECT * FROM image_lab_cases WHERE project_id = ? ORDER BY id DESC", (project["id"],)).fetchall()
            return [_row_to_dict(row) for row in rows]

    def run_attempt(
        self,
        project_slug: str,
        case_key: str,
        *,
        prompt_append: str = "",
        count: int = 4,
        seed: int | None = None,
    ) -> dict[str, Any]:
        count = max(1, min(12, int(count)))
        with self.db.connection() as conn:
            case = self.get_case(project_slug, case_key, conn=conn)
            attempt_key = next_key(conn, "image_lab_attempts", "attempt_key", "ATT", where="case_id = ?", params=(case["id"],))
            case_dir = self.asset_store.safe_resolve(case["case_dir"])
            attempt_dir = case_dir / "attempts" / attempt_key
            snapshot = self.asset_store.read_json(case_dir / "input_snapshot.json")
            prompt = self._attempt_prompt(snapshot, prompt_append=prompt_append)
            self.asset_store.write_text(attempt_dir / "prompt.md", prompt)
            candidates = self._generate_dummy_candidates(attempt_dir / "candidates", snapshot=snapshot, count=count, seed=seed)
            candidate_manifest = {"case_key": case_key, "attempt_key": attempt_key, "candidates": candidates, "prompt_append": prompt_append}
            review_payload = {"case_key": case_key, "attempt_key": attempt_key, "candidate_reviews": {}}
            self.asset_store.write_json(attempt_dir / "candidate_manifest.json", candidate_manifest)
            self.asset_store.write_json(attempt_dir / "operator_review.json", review_payload)
            conn.execute(
                """
                INSERT INTO image_lab_attempts(case_id, attempt_key, prompt_markdown_path, candidate_manifest_path, review_json_path)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    case["id"],
                    attempt_key,
                    self.asset_store.relative_to_workspace(attempt_dir / "prompt.md"),
                    self.asset_store.relative_to_workspace(attempt_dir / "candidate_manifest.json"),
                    self.asset_store.relative_to_workspace(attempt_dir / "operator_review.json"),
                ),
            )
            self.asset_store.write_text(attempt_dir / "attempt_summary.md", _attempt_summary_markdown(candidate_manifest))
            return {"case_key": case_key, "attempt_key": attempt_key, "candidate_count": len(candidates), "attempt_dir": self.asset_store.relative_to_workspace(attempt_dir)}

    def review_candidate(
        self,
        project_slug: str,
        case_key: str,
        attempt_key: str,
        candidate_id: str,
        *,
        decision: str,
        rating: int | None = None,
        notes: str = "",
        success_tags: list[str] | None = None,
        failure_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        decision = decision.strip().lower()
        if decision not in IMAGE_LAB_DECISIONS:
            raise ValueError(f"Unsupported Image Lab decision: {decision}")
        if rating is not None and not 1 <= int(rating) <= 5:
            raise ValueError("rating must be between 1 and 5")
        with self.db.connection() as conn:
            case = self.get_case(project_slug, case_key, conn=conn)
            attempt = self.get_attempt(conn, case_id=case["id"], attempt_key=attempt_key)
            review_path = self.asset_store.safe_resolve(attempt["review_json_path"])
            review = self.asset_store.read_json(review_path)
            review.setdefault("candidate_reviews", {})[candidate_id] = {
                "candidate_id": candidate_id,
                "decision": decision,
                "rating": rating,
                "notes": notes,
                "success_tags": success_tags or [],
                "failure_tags": failure_tags or [],
            }
            self.asset_store.write_json(review_path, review)
            if decision == "accepted":
                conn.execute("UPDATE image_lab_attempts SET status = 'accepted', notes = ? WHERE id = ?", (notes, attempt["id"]))
                conn.execute("UPDATE image_lab_cases SET accepted_attempt_key = ?, status = 'accepted', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (attempt_key, case["id"]))
            return {"case_key": case_key, "attempt_key": attempt_key, "candidate_id": candidate_id, "decision": decision, "rating": rating}

    def compare_attempts(self, project_slug: str, case_key: str) -> dict[str, Any]:
        with self.db.connection() as conn:
            case = self.get_case(project_slug, case_key, conn=conn)
            attempts = conn.execute("SELECT * FROM image_lab_attempts WHERE case_id = ? ORDER BY id", (case["id"],)).fetchall()
            rows: list[dict[str, Any]] = []
            for attempt in attempts:
                manifest = self.asset_store.read_json(self.asset_store.safe_resolve(attempt["candidate_manifest_path"]))
                review = self.asset_store.read_json(self.asset_store.safe_resolve(attempt["review_json_path"]))
                reviews = review.get("candidate_reviews", {}) if isinstance(review, dict) else {}
                ratings = [int(item["rating"]) for item in reviews.values() if isinstance(item, dict) and item.get("rating")]
                rows.append({
                    "attempt_key": attempt["attempt_key"],
                    "status": attempt["status"],
                    "candidate_count": len(manifest.get("candidates", [])),
                    "reviewed_count": len(reviews),
                    "best_rating": max(ratings) if ratings else None,
                    "accepted_count": sum(1 for item in reviews.values() if isinstance(item, dict) and item.get("decision") == "accepted"),
                    "failure_tags": _tag_counts(reviews, "failure_tags"),
                    "success_tags": _tag_counts(reviews, "success_tags"),
                })
            comparison = {"case_key": case_key, "attempt_count": len(rows), "attempts": rows, "accepted_attempt_key": case["accepted_attempt_key"]}
            case_dir = self.asset_store.safe_resolve(case["case_dir"])
            self.asset_store.write_json(case_dir / "comparison.json", comparison)
            self.asset_store.write_text(case_dir / "comparison.md", _comparison_markdown(comparison))
            return comparison

    def write_recommendation(self, project_slug: str, case_key: str, *, notes: str = "") -> dict[str, Any]:
        comparison = self.compare_attempts(project_slug, case_key)
        with self.db.connection() as conn:
            case = self.get_case(project_slug, case_key, conn=conn)
            case_dir = self.asset_store.safe_resolve(case["case_dir"])
            path = case_dir / "workback_recommendation.md"
            self.asset_store.write_text(path, _recommendation_markdown(case, comparison, notes))
            return {"case_key": case_key, "recommendation_path": self.asset_store.relative_to_workspace(path), "accepted_attempt_key": case["accepted_attempt_key"]}

    def get_case(self, project_slug: str, case_key: str, *, conn: Connection | None = None) -> Row:
        close = False
        if conn is None:
            conn = self.db.connect()
            close = True
        try:
            project = self.projects.get_project(project_slug, conn=conn)
            row = conn.execute("SELECT * FROM image_lab_cases WHERE project_id = ? AND case_key = ?", (project["id"], case_key)).fetchone()
            if row is None:
                raise KeyError(f"Image Lab case not found: {case_key}")
            return row
        finally:
            if close:
                conn.close()

    def get_attempt(self, conn: Connection, *, case_id: int, attempt_key: str) -> Row:
        row = conn.execute("SELECT * FROM image_lab_attempts WHERE case_id = ? AND attempt_key = ?", (case_id, attempt_key)).fetchone()
        if row is None:
            raise KeyError(f"Image Lab attempt not found: {attempt_key}")
        return row

    def _card_snapshot(self, card: Row, prompt: Row) -> dict[str, Any]:
        return {
            "card_key": card["card_key"],
            "name": card["name"],
            "card_type": card["card_type"],
            "rules_text": card["rules_text"],
            "art_direction": card["art_direction"],
            "positive_prompt": prompt["positive_prompt"],
            "negative_prompt": prompt["negative_prompt"],
            "prompt_json": _json_loads(prompt["prompt_json"], {}),
        }

    def _attempt_prompt(self, snapshot: dict[str, Any], *, prompt_append: str) -> str:
        positive = str(snapshot.get("positive_prompt") or snapshot.get("art_direction") or "").strip()
        if prompt_append.strip():
            positive = positive.rstrip() + ", " + prompt_append.strip()
        return "\n".join([
            "# Image Lab Attempt Prompt", "", "## Positive Prompt", positive, "", "## Negative Prompt", str(snapshot.get("negative_prompt") or "text, watermark, card border"), "", "## Operator Notes", prompt_append.strip(), "",
        ])

    def _generate_dummy_candidates(self, output_dir: Path, *, snapshot: dict[str, Any], count: int, seed: int | None) -> list[dict[str, Any]]:
        rng = random.Random(seed if seed is not None else 7000)
        output_dir = self.asset_store.safe_resolve(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        candidates: list[dict[str, Any]] = []
        for index in range(1, count + 1):
            candidate_id = f"LAB_CAND_{index:03d}"
            path = output_dir / f"{candidate_id}.png"
            self._draw_lab_image(str(snapshot.get("name") or "Card Art"), path, rng=rng, variant=index)
            candidates.append({"candidate_id": candidate_id, "image_path": self.asset_store.relative_to_workspace(path), "seed": rng.randint(1, 999999), "status": "generated"})
        return candidates

    def _draw_lab_image(self, title: str, path: Path, *, rng: random.Random, variant: int) -> None:
        width, height = 1024, 768
        base = (rng.randint(35, 95), rng.randint(35, 85), rng.randint(55, 130))
        accent = (rng.randint(130, 235), rng.randint(120, 210), rng.randint(95, 210))
        img = Image.new("RGB", (width, height), base)
        draw = ImageDraw.Draw(img)
        for _ in range(24):
            x0 = rng.randint(-80, width)
            y0 = rng.randint(-80, height)
            x1 = x0 + rng.randint(80, 320)
            y1 = y0 + rng.randint(60, 260)
            draw.rectangle((x0, y0, x1, y1), outline=accent, width=rng.randint(2, 6))
        draw.ellipse((340, 110, 690, 610), fill=(225, 218, 196), outline=(30, 25, 40), width=8)
        draw.rectangle((0, 625, width, height), fill=(28, 24, 34))
        _center_text(draw, f"{title[:28]} · V{variant}", (40, 645, 984, 725))
        img.save(path)


def _workback_notes(card: Row, prompt: Row, notes: str) -> str:
    return "\n".join([
        "# Image Lab Workback Notes", "", f"- Card: {card['card_key']} / {card['name']}", "- Production artifacts are read-only in this lab.", "", "## Baseline Art Direction", card["art_direction"] or "(missing)", "", "## Baseline Positive Prompt", prompt["positive_prompt"], "", "## Operator Goal", notes or "Narrow down the strongest prompt wording and composition family.", "",
    ])


def _attempt_summary_markdown(manifest: dict[str, Any]) -> str:
    lines = ["# Image Lab Attempt", "", f"- Case: {manifest['case_key']}", f"- Attempt: {manifest['attempt_key']}", f"- Candidates: {len(manifest['candidates'])}", ""]
    for item in manifest["candidates"]:
        lines.append(f"- {item['candidate_id']}: `{item['image_path']}`")
    return "\n".join(lines) + "\n"


def _comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = ["# Image Lab Comparison", "", f"- Case: {comparison['case_key']}", f"- Attempts: {comparison['attempt_count']}", "", "| Attempt | Status | Candidates | Reviewed | Best Rating | Accepted |", "|---|---|---:|---:|---:|---:|"]
    for row in comparison["attempts"]:
        lines.append(f"| {row['attempt_key']} | {row['status']} | {row['candidate_count']} | {row['reviewed_count']} | {row.get('best_rating') or ''} | {row['accepted_count']} |")
    return "\n".join(lines) + "\n"


def _recommendation_markdown(case: Row, comparison: dict[str, Any], notes: str) -> str:
    return "\n".join([
        "# Image Lab Workback Recommendation", "", f"- Case: {case['case_key']}", f"- Target: {case['target_type']} / {case['target_id']}", f"- Accepted attempt: {case['accepted_attempt_key'] or '(none yet)'}", "", "## Recommendation", notes or "Compare accepted/rejected attempts and copy only the prompt wording that produced better card art candidates.", "", "## Comparison Summary", "```json", json.dumps(comparison, indent=2, ensure_ascii=False), "```", "",
    ])


def _tag_counts(reviews: dict[str, Any], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for review in reviews.values():
        if not isinstance(review, dict):
            continue
        for tag in review.get(key, []) or []:
            tag = str(tag).strip().lower()
            if tag:
                counts[tag] = counts.get(tag, 0) + 1
    return counts


def _center_text(draw: ImageDraw.ImageDraw, text: str, box: tuple[int, int, int, int]) -> None:
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 42)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    x = box[0] + ((box[2] - box[0]) - (bbox[2] - bbox[0])) // 2
    y = box[1] + ((box[3] - box[1]) - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), text, font=font, fill=(238, 229, 202))


def _row_to_dict(row: Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _json_loads(value: Any, default: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except json.JSONDecodeError:
        return default
