from __future__ import annotations

from pathlib import Path

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db, read_text_arg
from cardforge.domain.enums import JobType
from cardforge.services.jobs.job_service import JobService

app = typer.Typer(help="Local job queue commands")


@app.command("list")
def job_list(
    project_slug: str,
    status: str | None = typer.Option(None, "--status", help="Filter by pending/running/completed/failed."),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    ensure_db()
    for row in JobService().list_jobs(project_slug, status=status, limit=limit):
        typer.echo(
            f"{row['id']}\t{row['job_type']}\t{row['target_type']}:{row['target_id']}\t"
            f"{row['status']}\tattempts={row['attempt_count']}/{row['max_attempts']}"
        )


@app.command("show")
def job_show(project_slug: str, job_id: int) -> None:
    ensure_db()
    matches = [row for row in JobService().list_jobs(project_slug, limit=500) if int(row["id"]) == job_id]
    if not matches:
        raise typer.BadParameter(f"Job not found in project {project_slug}: {job_id}")
    echo_json(matches[0])


@app.command("run-next")
def job_run_next(project_slug: str) -> None:
    ensure_db()
    result = JobService().run_next(project_slug)
    echo_json({"ran": False, "message": "No pending job."} if result is None else result.to_dict())


@app.command("run-all")
def job_run_all(project_slug: str, limit: int = typer.Option(20, "--limit")) -> None:
    ensure_db()
    echo_json(JobService().run_all(project_slug, limit=limit))


@app.command("retry")
def job_retry(project_slug: str, job_id: int) -> None:
    ensure_db()
    echo_json(JobService().retry(project_slug, job_id))


@app.command("requeue-stale")
def job_requeue_stale(older_than_minutes: int = typer.Option(60, "--older-than-minutes")) -> None:
    ensure_db()
    echo_json(JobService().requeue_stale_running(older_than_minutes=older_than_minutes))


@app.command("enqueue-batch-generate")
def enqueue_batch_generate(
    project_slug: str,
    set_code: str,
    count: int = typer.Option(12, "--count"),
    request: str = typer.Option("", "--request"),
    request_file: Path | None = typer.Option(None, "--request-file"),
) -> None:
    ensure_db()
    request_text = read_text_arg(request, request_file) or "Generate a balanced prototype card batch."
    echo_json(
        JobService().enqueue(
            project_slug,
            job_type=JobType.BATCH_GENERATE,
            target_type="set",
            target_id=set_code,
            payload={"set_code": set_code, "count": count, "request_text": request_text, "use_mock": True},
        )
    )


@app.command("enqueue-render-card")
def enqueue_render_card(
    project_slug: str,
    card_key: str,
    placeholder_art: bool = typer.Option(True, "--placeholder-art/--locked-art"),
) -> None:
    ensure_db()
    echo_json(
        JobService().enqueue(
            project_slug,
            job_type=JobType.RENDER_CARD,
            target_type="card",
            target_id=card_key,
            payload={"card_key": card_key, "placeholder_art": placeholder_art},
        )
    )


@app.command("enqueue-dummy-art")
def enqueue_dummy_art(
    project_slug: str,
    card_key: str,
    count: int = typer.Option(4, "--count"),
) -> None:
    ensure_db()
    echo_json(
        JobService().enqueue(
            project_slug,
            job_type=JobType.ART_GENERATE_DUMMY,
            target_type="card",
            target_id=card_key,
            payload={"card_key": card_key, "count": count},
        )
    )


@app.command("enqueue-export")
def enqueue_export(project_slug: str, set_code: str, export_type: str = typer.Option("json", "--type")) -> None:
    ensure_db()
    job_type_by_export = {
        "json": JobType.EXPORT_JSON,
        "csv": JobType.EXPORT_CSV,
        "markdown": JobType.EXPORT_MARKDOWN,
        "png": JobType.EXPORT_PNG,
    }
    job_type = job_type_by_export.get(export_type)
    if job_type is None:
        raise typer.BadParameter("Export type must be one of: json, csv, markdown, png")
    echo_json(
        JobService().enqueue(
            project_slug,
            job_type=job_type,
            target_type="set",
            target_id=set_code,
            payload={"set_code": set_code},
        )
    )
