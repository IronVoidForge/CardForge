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
