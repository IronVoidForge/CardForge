from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.art.art_candidate_service import ArtCandidateService
from cardforge.services.art.art_prompt_service import ArtPromptService
from cardforge.services.review.auto_review_service import AutoReviewService

app = typer.Typer(help="Art prompt/candidate commands")


@app.command("prompt")
def art_prompt(project_slug: str, card_key: str) -> None:
    ensure_db()
    echo_json(ArtPromptService().create_prompt(project_slug, card_key))


@app.command("generate-dummy")
def art_generate_dummy(
    project_slug: str,
    card_key: str,
    count: int = typer.Option(4, "--count"),
    seed: int | None = None,
) -> None:
    ensure_db()
    echo_json(ArtCandidateService().generate_dummy_candidates(project_slug, card_key, count=count, seed=seed))


@app.command("list")
def art_list(project_slug: str, card_key: str) -> None:
    ensure_db()
    for row in ArtCandidateService().list_candidates(project_slug, card_key):
        typer.echo(f"{row['candidate_key']}\t{row['status']}\t{row['image_path']}")


@app.command("approve")
def art_approve(project_slug: str, candidate_key: str) -> None:
    ensure_db()
    echo_json(ArtCandidateService().approve(project_slug, candidate_key))


@app.command("reject")
def art_reject(project_slug: str, candidate_key: str, reason: str = "") -> None:
    ensure_db()
    echo_json(ArtCandidateService().reject(project_slug, candidate_key, reason=reason))


@app.command("auto-review")
def art_auto_review(project_slug: str, candidate_key: str) -> None:
    ensure_db()
    echo_json(AutoReviewService().review_art_candidate(project_slug, candidate_key))


@app.command("lock")
def art_lock(project_slug: str, candidate_key: str) -> None:
    ensure_db()
    echo_json(ArtCandidateService().lock(project_slug, candidate_key))
