from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    LOCKED = "locked"
    ARCHIVED = "archived"


class CardStatus(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    VALIDATED = "validated"
    NEEDS_REPAIR = "needs_repair"
    TEXT_APPROVED = "text_approved"
    ART_PENDING = "art_pending"
    ART_READY = "art_ready"
    RENDERED = "rendered"
    RENDER_APPROVED = "render_approved"
    LOCKED = "locked"
    REJECTED = "rejected"


class ReviewStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REWORK = "needs_rework"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REWORK = "request_rework"
    LOCK = "lock"
    UNLOCK = "unlock"
    DEFER = "defer"


class RenderStatus(StrEnum):
    RENDERED = "rendered"
    LAYOUT_WARNING = "layout_warning"
    APPROVED = "approved"
    LOCKED = "locked"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    BATCH_GENERATE = "batch_generate"
    BATCH_VALIDATE = "batch_validate"
    BATCH_AUTO_REVIEW = "batch_auto_review"
    CARD_AUTOFILL = "card_autofill"
    CARD_REFINE = "card_refine"
    CARD_AUTO_REVIEW = "card_auto_review"
    ART_GENERATE_DUMMY = "art_generate_dummy"
    ART_PREPARE_COMFY = "art_prepare_comfy"
    ART_SUBMIT_COMFY = "art_submit_comfy"
    ART_AUTO_REVIEW = "art_auto_review"
    PROMPT_LAB_RUN = "prompt_lab_run"
    IMAGE_LAB_RUN = "image_lab_run"
    RENDER_CARD = "render_card"
    EXPORT_JSON = "export_json"
    EXPORT_CSV = "export_csv"
    EXPORT_MARKDOWN = "export_markdown"
    EXPORT_PNG = "export_png"


class ResumeActionType(StrEnum):
    GENERATE_BATCH = "generate_batch"
    REVIEW_BATCH = "review_batch"
    RESOLVE_AUTO_REVIEW = "resolve_auto_review"
    GENERATE_ART = "generate_art"
    LOCK_ART = "lock_art"
    RENDER_CARDS = "render_cards"
    REVIEW_QUEUE = "review_queue"
    EXPORT = "export"
    NONE = "none"
