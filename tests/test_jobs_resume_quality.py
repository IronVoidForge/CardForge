from __future__ import annotations

from cardforge.db.session import Database
from cardforge.domain.enums import JobStatus, JobType
from cardforge.services.jobs.job_service import JobService
from cardforge.services.observability.diagnostics_service import DiagnosticsService
from cardforge.services.projects.project_service import ProjectService
from cardforge.services.resume.resume_service import ResumeService
from cardforge.services.sets.set_service import SetService


def _setup(db: Database) -> None:
    ProjectService(db).create_project("gravebound_test", name="Gravebound Test")
    SetService(db).create_set("gravebound_test", name="Gravebound Dominion")


def test_job_queue_runs_batch_generation_and_audits(db: Database) -> None:
    _setup(db)
    service = JobService(db)
    job = service.enqueue(
        "gravebound_test",
        job_type=JobType.BATCH_GENERATE,
        target_type="set",
        target_id="SET001",
        payload={"set_code": "SET001", "count": 3, "request_text": "Generate gothic cards."},
    )
    assert job["status"] == JobStatus.PENDING.value

    result = service.run_next("gravebound_test")
    assert result is not None
    assert result.status == JobStatus.COMPLETED
    assert result.result["created_card_count"] == 3

    jobs = service.list_jobs("gravebound_test")
    assert jobs[0]["status"] == JobStatus.COMPLETED.value
    with db.connection() as conn:
        card_count = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        audit_count = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    assert card_count == 3
    assert audit_count >= 3


def test_job_failure_and_retry(db: Database) -> None:
    _setup(db)
    service = JobService(db)
    job = service.enqueue(
        "gravebound_test",
        job_type=JobType.RENDER_CARD,
        target_type="card",
        target_id="CARD_MISSING",
        payload={"card_key": "CARD_MISSING"},
    )
    result = service.run_next("gravebound_test")
    assert result is not None
    assert result.status == JobStatus.FAILED

    retried = service.retry("gravebound_test", int(job["id"]))
    assert retried["status"] == JobStatus.PENDING.value


def test_resume_plan_suggests_next_safe_job(db: Database) -> None:
    _setup(db)
    plan = ResumeService(db).plan_project("gravebound_test", set_code="SET001")
    assert plan["action_type"] == "generate_batch"
    assert plan["suggested_jobs"][0]["job_type"] == JobType.BATCH_GENERATE.value

    JobService(db).enqueue(
        "gravebound_test",
        job_type=JobType.BATCH_GENERATE,
        target_type="set",
        target_id="SET001",
        payload={"set_code": "SET001", "count": 1, "request_text": "one card"},
    )
    queued_plan = ResumeService(db).plan_project("gravebound_test", set_code="SET001")
    assert queued_plan["message"].startswith("Run or inspect queued jobs")


def test_diagnostics_service_reports_ok(db: Database) -> None:
    assert DiagnosticsService(db).check()["ok"] is True
