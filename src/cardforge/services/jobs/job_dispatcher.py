from __future__ import annotations

from typing import Any, Callable

from cardforge.db.session import Database
from cardforge.domain.enums import JobType
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.batches.card_batch_service import CardBatchService
from cardforge.services.comfy.comfy_art_service import ComfyArtService
from cardforge.services.export.export_service import ExportService
from cardforge.services.labs.image_lab_service import ImageLabService
from cardforge.services.labs.prompt_lab_service import PromptLabService
from cardforge.services.generation.card_autofill_service import CardAutofillService
from cardforge.services.refinement.card_refinement_service import CardRefinementService
from cardforge.services.render.card_renderer import CardRenderer
from cardforge.services.review.auto_review_service import AutoReviewService

JobHandler = Callable[[dict[str, Any]], dict[str, Any]]


class JobDispatcher:
    """Dispatch offline-safe jobs to small focused services.

    The dispatcher is deliberately boring: it validates required payload keys and
    calls existing services. Live LM Studio/ComfyUI jobs can plug in here later
    without changing the queue schema or UI.
    """

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def dispatch(self, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers: dict[str, JobHandler] = {
            JobType.BATCH_GENERATE.value: self._batch_generate,
            JobType.BATCH_VALIDATE.value: self._batch_validate,
            JobType.BATCH_AUTO_REVIEW.value: self._batch_auto_review,
            JobType.CARD_AUTOFILL.value: self._card_autofill,
            JobType.CARD_REFINE.value: self._card_refine,
            JobType.CARD_AUTO_REVIEW.value: self._card_auto_review,
            JobType.ART_GENERATE_DUMMY.value: self._art_generate_dummy,
            JobType.ART_PREPARE_COMFY.value: self._art_prepare_comfy,
            JobType.ART_SUBMIT_COMFY.value: self._art_submit_comfy,
            JobType.ART_AUTO_REVIEW.value: self._art_auto_review,
            JobType.PROMPT_LAB_RUN.value: self._prompt_lab_run,
            JobType.IMAGE_LAB_RUN.value: self._image_lab_run,
            JobType.RENDER_CARD.value: self._render_card,
            JobType.EXPORT_JSON.value: self._export_json,
            JobType.EXPORT_CSV.value: self._export_csv,
            JobType.EXPORT_MARKDOWN.value: self._export_markdown,
            JobType.EXPORT_PNG.value: self._export_png,
        }
        handler = handlers.get(job_type)
        if handler is None:
            raise ValueError(f"Unsupported job type: {job_type}")
        return handler(dict(payload))

    def _batch_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return CardBatchService(self.db).generate_batch(
            self._required(payload, "project_slug"),
            self._required(payload, "set_code"),
            count=int(payload.get("count", 12)),
            request_text=str(payload.get("request_text") or "Generate a balanced card batch."),
            use_mock=bool(payload.get("use_mock", True)),
        )

    def _batch_validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return CardBatchService(self.db).validate_batch(
            self._required(payload, "project_slug"),
            self._required(payload, "batch_key"),
        )

    def _batch_auto_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return AutoReviewService(self.db).review_batch_text(
            self._required(payload, "project_slug"),
            self._required(payload, "batch_key"),
        )

    def _card_autofill(self, payload: dict[str, Any]) -> dict[str, Any]:
        return CardAutofillService(self.db).autofill_card(
            self._required(payload, "project_slug"),
            self._required(payload, "card_key"),
        )

    def _card_refine(self, payload: dict[str, Any]) -> dict[str, Any]:
        return CardRefinementService(self.db).refine_card(
            self._required(payload, "project_slug"),
            self._required(payload, "card_key"),
        )

    def _card_auto_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return AutoReviewService(self.db).review_card_text(
            self._required(payload, "project_slug"),
            self._required(payload, "card_key"),
        )

    def _art_generate_dummy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return ArtCandidateService(self.db).generate_dummy_candidates(
            self._required(payload, "project_slug"),
            self._required(payload, "card_key"),
            count=int(payload.get("count", 4)),
            seed=int(payload["seed"]) if payload.get("seed") not in {None, ""} else None,
        )

    def _art_prepare_comfy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return ComfyArtService(self.db).prepare_card_art(
            self._required(payload, "project_slug"),
            self._required(payload, "card_key"),
            workflow_key=str(payload.get("workflow_key") or "stub.card_art.t2i.v1"),
            seed=int(payload["seed"]) if payload.get("seed") not in {None, ""} else None,
            width=int(payload["width"]) if payload.get("width") not in {None, ""} else None,
            height=int(payload["height"]) if payload.get("height") not in {None, ""} else None,
            submit=False,
        )

    def _art_submit_comfy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return ComfyArtService(self.db).prepare_card_art(
            self._required(payload, "project_slug"),
            self._required(payload, "card_key"),
            workflow_key=str(payload.get("workflow_key") or "stub.card_art.t2i.v1"),
            seed=int(payload["seed"]) if payload.get("seed") not in {None, ""} else None,
            width=int(payload["width"]) if payload.get("width") not in {None, ""} else None,
            height=int(payload["height"]) if payload.get("height") not in {None, ""} else None,
            submit=True,
        )

    def _art_auto_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return AutoReviewService(self.db).review_art_candidate(
            self._required(payload, "project_slug"),
            self._required(payload, "candidate_key"),
        )

    def _prompt_lab_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return PromptLabService(self.db).run_case(
            self._required(payload, "project_slug"),
            self._required(payload, "case_key"),
            variant_notes=str(payload.get("variant_notes") or ""),
            use_mock=True,
        )

    def _image_lab_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return ImageLabService(self.db).run_attempt(
            self._required(payload, "project_slug"),
            self._required(payload, "case_key"),
            prompt_append=str(payload.get("prompt_append") or ""),
            count=int(payload.get("count", 4)),
            seed=int(payload["seed"]) if payload.get("seed") not in {None, ""} else None,
        )

    def _render_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        return CardRenderer(self.db).render_card(
            self._required(payload, "project_slug"),
            self._required(payload, "card_key"),
            placeholder_art=bool(payload.get("placeholder_art", True)),
        )

    def _export_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        return ExportService(self.db).export_json(self._required(payload, "project_slug"), self._required(payload, "set_code"))

    def _export_csv(self, payload: dict[str, Any]) -> dict[str, Any]:
        return ExportService(self.db).export_csv(self._required(payload, "project_slug"), self._required(payload, "set_code"))

    def _export_markdown(self, payload: dict[str, Any]) -> dict[str, Any]:
        return ExportService(self.db).export_markdown_catalog(
            self._required(payload, "project_slug"), self._required(payload, "set_code")
        )

    def _export_png(self, payload: dict[str, Any]) -> dict[str, Any]:
        return ExportService(self.db).export_png_bundle(self._required(payload, "project_slug"), self._required(payload, "set_code"))

    def _required(self, payload: dict[str, Any], key: str) -> str:
        value = str(payload.get(key) or "").strip()
        if not value:
            raise ValueError(f"Job payload missing required field: {key}")
        return value
