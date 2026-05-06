from __future__ import annotations

from pathlib import Path

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db, read_text_arg
from cardforge.services.balance.balance_review_service import BalanceReviewService
from cardforge.services.batches.card_batch_service import CardBatchService
from cardforge.services.generation.rules_review_service import RulesReviewService
from cardforge.services.review.auto_review_service import AutoReviewService

app = typer.Typer(help="Batch generation commands")


@app.command("generate")
def batch_generate(
    project_slug: str,
    set_code: str,
    count: int = typer.Option(12, "--count", help="Number of cards to generate."),
    request: str = typer.Option("", "--request", help="Freeform batch request."),
    request_file: Path | None = typer.Option(None, "--request-file", help="Read request from markdown/text file."),
    live: bool = typer.Option(False, "--live", help="Call LM Studio instead of deterministic offline simulation."),
) -> None:
    ensure_db()
    request_text = read_text_arg(request, request_file) or "Generate a balanced gothic fantasy card batch."
    result = CardBatchService().generate_batch(project_slug, set_code, count=count, request_text=request_text, use_mock=not live)
    echo_json(result)


@app.command("list")
def batch_list(project_slug: str, set_code: str | None = None) -> None:
    ensure_db()
    for row in CardBatchService().list_batches(project_slug, set_code):
        typer.echo(f"{row['batch_key']}\t{row['target_count']}\t{row['status']}")


@app.command("show")
def batch_show(project_slug: str, batch_key: str) -> None:
    ensure_db()
    row = CardBatchService().get_batch(project_slug, batch_key)
    echo_json({key: row[key] for key in row.keys()})


@app.command("validate")
def batch_validate(project_slug: str, batch_key: str) -> None:
    ensure_db()
    echo_json(CardBatchService().validate_batch(project_slug, batch_key))


@app.command("auto-review")
def batch_auto_review(project_slug: str, batch_key: str) -> None:
    ensure_db()
    echo_json(AutoReviewService().review_batch_text(project_slug, batch_key))


@app.command("balance-review")
def batch_balance_review(project_slug: str, batch_key: str) -> None:
    ensure_db()
    echo_json(BalanceReviewService().review_batch(project_slug, batch_key))


@app.command("rules-review")
def batch_rules_review(project_slug: str, batch_key: str) -> None:
    ensure_db()
    echo_json(RulesReviewService().review_batch(project_slug, batch_key))
