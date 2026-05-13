from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from cardforge.db.session import Database
from cardforge.domain.ids import next_key
from cardforge.files.asset_store import AssetStore
from cardforge.integrations.comfyui import ComfyClient
from cardforge.services.art.art_prompt_service import ArtPromptService
from cardforge.services.cards.card_service import CardService
from cardforge.services.comfy.workflow_defaults import DEFAULT_CARD_ART_WORKFLOW_KEY
from cardforge.services.comfy.workflow_patcher import WorkflowPatcher
from cardforge.services.comfy.workflow_registry_service import WorkflowRegistryService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.review.review_service import ReviewService


class ComfyArtService:
    """Prepares and optionally submits ComfyUI card art jobs.

    The default path is `submit=False`, which writes a patched workflow and DB
    row without requiring ComfyUI.  This keeps tests offline while making the
    live integration path explicit and reviewable.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.asset_store = AssetStore(self.db.settings)
        self.projects = ProjectService(self.db)
        self.cards = CardService(self.db)
        self.prompts = ArtPromptService(self.db)
        self.registry = WorkflowRegistryService(self.db)
        self.patcher = WorkflowPatcher()

    def prepare_card_art(
        self,
        project_slug: str,
        card_key: str,
        *,
        workflow_key: str = DEFAULT_CARD_ART_WORKFLOW_KEY,
        seed: int | None = None,
        width: int | None = None,
        height: int | None = None,
        submit: bool = False,
    ) -> dict[str, Any]:
        self.registry.sync_defaults()
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            card = self.cards.get_card(project_slug, card_key, conn=conn)
            prompt_row = conn.execute("SELECT * FROM art_prompts WHERE card_id = ? ORDER BY version_number DESC LIMIT 1", (card["id"],)).fetchone()
            if prompt_row is None:
                created = self.prompts.create_prompt(project_slug, card_key)
                prompt_row = conn.execute("SELECT * FROM art_prompts WHERE id = ?", (created["art_prompt_id"],)).fetchone()
            workflow_row = self.registry.get_workflow(workflow_key, conn=conn)
            workflow_payload = self.registry.load_workflow_payload(workflow_row)
            defaults = self.registry.default_settings(workflow_row)
            next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM comfy_jobs").fetchone()["next_id"]
            job_key = f"COMFY_{int(next_id):04d}"
            save_prefix = f"cardforge/{project_slug}/{card_key}/{job_key.lower()}"
            patch_values = {
                "positive_prompt": prompt_row["positive_prompt"],
                "negative_prompt": prompt_row["negative_prompt"],
                "seed": seed if seed is not None else 1000 + int(card["id"]),
                "width": width or defaults.get("width", 1024),
                "height": height or defaults.get("height", 768),
                "batch_size": defaults.get("batch_size", 1),
                "save_prefix": save_prefix,
            }
            patched = self.patcher.patch(workflow_payload, self.registry.patch_points(workflow_row), patch_values)
            root = self.asset_store.project_root(project_slug) / "logs" / "comfy" / job_key
            patched_path = root / "patched_workflow.json"
            manifest_path = root / "COMFY_JOB_MANIFEST.json"
            self.asset_store.write_json(patched_path, patched)
            conn.execute(
                """
                INSERT INTO comfy_jobs(workflow_id, seed, positive_prompt, negative_prompt, settings_json, patched_workflow_path, status)
                VALUES(?, ?, ?, ?, ?, ?, 'prepared')
                """,
                (workflow_row["id"], int(patch_values["seed"]), prompt_row["positive_prompt"], prompt_row["negative_prompt"], json.dumps({"patch_values": patch_values, "submit_requested": submit}, ensure_ascii=False), self.asset_store.relative_to_workspace(patched_path)),
            )
            comfy_job_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            result = {"project_slug": project_slug, "card_key": card_key, "workflow_key": workflow_key, "comfy_job_id": comfy_job_id, "status": "prepared", "patched_workflow_path": self.asset_store.relative_to_workspace(patched_path), "save_prefix": save_prefix, "manifest_path": self.asset_store.relative_to_workspace(manifest_path)}
            if submit:
                client = ComfyClient(self.db.settings)
                submission = client.submit_prompt(patched)
                if not submission.ok:
                    conn.execute("UPDATE comfy_jobs SET status = 'failed', error_message = ? WHERE id = ?", (submission.error, comfy_job_id))
                    raise RuntimeError(submission.error or "ComfyUI submit failed.")
                conn.execute("UPDATE comfy_jobs SET status = 'submitted', prompt_id = ?, submitted_at = CURRENT_TIMESTAMP WHERE id = ?", (submission.prompt_id, comfy_job_id))
                result.update({"status": "submitted", "prompt_id": submission.prompt_id})
                history = client.wait_for_completion(submission.prompt_id)
                imported = self._import_completed_images(
                    conn=conn,
                    project_id=project["id"],
                    set_id=card["set_id"],
                    project_slug=project_slug,
                    card_id=card["id"],
                    card_key=card_key,
                    prompt_id=submission.prompt_id,
                    comfy_job_id=comfy_job_id,
                    art_prompt_id=prompt_row["id"],
                    workflow_key=workflow_key,
                    seed=int(patch_values["seed"]),
                    history=history,
                    settings=patch_values,
                )
                conn.execute("UPDATE comfy_jobs SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?", (comfy_job_id,))
                result.update({"status": "completed", "candidate_keys": imported})
            self.asset_store.write_json(manifest_path, result)
            return result

    def _import_completed_images(
        self,
        *,
        conn: Any,
        project_id: int,
        set_id: int,
        project_slug: str,
        card_id: int,
        card_key: str,
        prompt_id: str,
        comfy_job_id: int,
        art_prompt_id: int,
        workflow_key: str,
        seed: int,
        history: dict[str, Any],
        settings: dict[str, Any],
    ) -> list[str]:
        image_refs = self._history_image_refs(history)
        if not image_refs:
            raise RuntimeError(f"ComfyUI completed prompt {prompt_id} without image outputs.")
        art_dir = self.asset_store.project_root(project_slug) / "cards" / card_key / "art" / "candidates"
        art_dir.mkdir(parents=True, exist_ok=True)
        created_keys: list[str] = []
        for image_ref in image_refs:
            source = self._resolve_comfy_output(image_ref)
            candidate_key = next_key(conn, "art_candidates", "candidate_key", "ART_CAND", where="card_id = ?", params=(card_id,))
            image_path = art_dir / f"{candidate_key}{source.suffix or '.png'}"
            thumb_path = art_dir / f"{candidate_key}_thumb.png"
            Image.open(source).save(image_path)
            Image.open(image_path).resize((256, 192)).save(thumb_path)
            conn.execute(
                """
                INSERT INTO art_candidates(card_id, art_prompt_id, comfy_job_id, candidate_key, image_path, thumbnail_path, seed, workflow_key, settings_json, status, review_status)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated', 'open')
                """,
                (
                    card_id,
                    art_prompt_id,
                    comfy_job_id,
                    candidate_key,
                    self.asset_store.relative_to_workspace(image_path),
                    self.asset_store.relative_to_workspace(thumb_path),
                    seed,
                    workflow_key,
                    json.dumps({"comfy": True, "prompt_id": prompt_id, "source": image_ref, **settings}, ensure_ascii=False),
                ),
            )
            created_keys.append(candidate_key)
        ReviewService(self.db).enqueue(
            project_id=project_id,
            set_id=set_id,
            target_type="card_art",
            target_id=card_key,
            review_type="art_candidate",
            title=f"Review Comfy art candidates: {card_key}",
            description=f"Imported {len(created_keys)} live ComfyUI art candidate(s).",
            metadata={"candidate_keys": created_keys, "comfy_job_id": comfy_job_id, "prompt_id": prompt_id},
            conn=conn,
        )
        return created_keys

    def _history_image_refs(self, history: dict[str, Any]) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        outputs = history.get("outputs", {}) if isinstance(history, dict) else {}
        for output in outputs.values():
            for image in output.get("images", []) if isinstance(output, dict) else []:
                if isinstance(image, dict) and image.get("filename"):
                    refs.append(
                        {
                            "filename": str(image.get("filename") or ""),
                            "subfolder": str(image.get("subfolder") or ""),
                            "type": str(image.get("type") or "output"),
                        }
                    )
        return refs

    def _resolve_comfy_output(self, image_ref: dict[str, str]) -> Path:
        output_root = Path(self.db.settings.comfy_output_dir).expanduser().resolve()
        candidate = (output_root / image_ref.get("subfolder", "") / image_ref["filename"]).resolve()
        candidate.relative_to(output_root)
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"ComfyUI output image not found: {candidate}")
        return candidate
