from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db, parse_csv_tags
from cardforge.services.rework.card_rework_service import CardReworkService
from cardforge.services.rework.rework_service import ReworkService

app = typer.Typer(help="Rework request commands")


@app.command("create")
def rework_create(
    project_slug: str,
    target_type: str,
    target_id: str,
    rework_type: str,
    reason: str = "",
    notes: str = "",
    tags: str = "",
) -> None:
    ensure_db()
    result = ReworkService().create_request(
        project_slug,
        target_type=target_type,
        target_id=target_id,
        rework_type=rework_type,
        reason=reason,
        operator_notes=notes,
        failure_tags=parse_csv_tags(tags),
    )
    echo_json(result)


@app.command("list")
def rework_list(project_slug: str) -> None:
    ensure_db()
    for row in ReworkService().list_requests(project_slug):
        typer.echo(f"{row['id']}\t{row['target_type']}:{row['target_id']}\t{row['rework_type']}\t{row['status']}")


@app.command("repair-rules")
def rework_repair_rules(project_slug: str, card_key: str, reason: str = "shorten for template") -> None:
    ensure_db()
    echo_json(CardReworkService().repair_rules_text(project_slug, card_key, reason=reason))
