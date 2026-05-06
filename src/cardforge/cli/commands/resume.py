from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.domain.enums import JobType
from cardforge.services.jobs.job_service import JobService
from cardforge.services.resume.resume_service import ResumeService

app = typer.Typer(help="Resume planning commands")


@app.command("plan")
def resume_plan(project_slug: str, set_code: str | None = typer.Option(None, "--set")) -> None:
    ensure_db()
    echo_json(ResumeService().plan_project(project_slug, set_code=set_code))


@app.command("enqueue-next")
def resume_enqueue_next(project_slug: str, set_code: str | None = typer.Option(None, "--set")) -> None:
    ensure_db()
    plan = ResumeService().plan_project(project_slug, set_code=set_code)
    jobs = plan.get("suggested_jobs", [])
    if not jobs:
        echo_json({"enqueued": False, "plan": plan})
        return
    first = jobs[0]
    result = JobService().enqueue(
        project_slug,
        job_type=JobType(first["job_type"]),
        target_type=first["target_type"],
        target_id=first["target_id"],
        payload=first.get("payload", {}),
    )
    echo_json({"enqueued": True, "job": result, "plan": plan})
