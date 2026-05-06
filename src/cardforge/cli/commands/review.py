from __future__ import annotations

import typer

from cardforge.cli.bootstrap import ensure_db, parse_csv_tags
from cardforge.domain.enums import ReviewDecision
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.review.review_service import ReviewService

app = typer.Typer(help="Review commands")


@app.command("list")
def review_list(project_slug: str) -> None:
    ensure_db()
    project = ProjectService().get_project(project_slug)
    rows = ReviewService().list_open(project["id"])
    if not rows:
        typer.echo("No open review items.")
        return
    for row in rows:
        typer.echo(f"{row['id']}\t{row['review_type']}\t{row['target_type']}:{row['target_id']}\t{row['title']}")


@app.command("decide")
def review_decide(review_item_id: int, decision: ReviewDecision, reason: str = "", tags: str = "") -> None:
    ensure_db()
    row = ReviewService().decide(
        review_item_id,
        decision=decision,
        reason=reason,
        tags=parse_csv_tags(tags),
    )
    typer.echo(f"Review {row['id']} now {row['status']}")
