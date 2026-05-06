from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.refinement.card_refinement_service import CardRefinementService
from cardforge.services.review.auto_review_service import AutoReviewService

app = typer.Typer(help="Offline auto-review and refinement commands")


@app.command("review-card")
def auto_review_card(project_slug: str, card_key: str) -> None:
    ensure_db()
    echo_json(AutoReviewService().review_card_text(project_slug, card_key))


@app.command("review-batch")
def auto_review_batch(project_slug: str, batch_key: str) -> None:
    ensure_db()
    echo_json(AutoReviewService().review_batch_text(project_slug, batch_key))


@app.command("refine-card")
def auto_refine_card(project_slug: str, card_key: str, live: bool = typer.Option(False, "--live")) -> None:
    ensure_db()
    echo_json(CardRefinementService().refine_card(project_slug, card_key, use_mock=not live))
