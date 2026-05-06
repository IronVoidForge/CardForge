from __future__ import annotations

import json
from sqlite3 import Row
from typing import Any

from cardforge.db.session import Database
from cardforge.domain.enums import JobStatus, JobType
from cardforge.services.jobs.job_dispatcher import JobDispatcher
from cardforge.services.jobs.job_models import JobCreateRequest, JobRunResult
from cardforge.services.jobs.job_repository import JobRepository
from cardforge.services.observability.audit_log_service import AuditLogService
from cardforge.services.projects.project_service import ProjectService


class JobService:
    """Queue, execute, retry, and inspect local offline jobs."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.projects = ProjectService(self.db)
        self.repo = JobRepository()
        self.dispatcher = JobDispatcher(self.db)
        self.audit = AuditLogService(self.db)

    def enqueue(
        self,
        project_slug: str,
        *,
        job_type: JobType,
        target_type: str,
        target_id: str,
        payload: dict[str, Any],
        priority: int = 100,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            merged_payload = {"project_slug": project_slug, **payload}
            row = self.repo.create(
                conn,
                JobCreateRequest(
                    project_id=project["id"],
                    job_type=job_type,
                    target_type=target_type,
                    target_id=target_id,
                    payload=merged_payload,
                    priority=priority,
                    max_attempts=max_attempts,
                ),
            )
            self.audit.record(
                conn,
                project_id=project["id"],
                event_type="job_enqueued",
                target_type="generation_job",
                target_id=str(row["id"]),
                payload={"job_type": job_type.value, "target_type": target_type, "target_id": target_id},
            )
            return self._row_to_dict(row)

    def list_jobs(self, project_slug: str, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            return [self._row_to_dict(row) for row in self.repo.list_for_project(conn, project["id"], status=status, limit=limit)]

    def run_next(self, project_slug: str | None = None) -> JobRunResult | None:
        project_id: int | None = None
        if project_slug:
            with self.db.connection() as conn:
                project_id = int(self.projects.get_project(project_slug, conn=conn)["id"])
        with self.db.connection() as conn:
            row = self.repo.next_pending(conn, project_id=project_id)
            if row is None:
                return None
            leased = self.repo.mark_running(conn, int(row["id"]))
            payload = json.loads(leased["payload_json"] or "{}")
            job_id = int(leased["id"])
            job_type = str(leased["job_type"])
            project_id_for_audit = int(leased["project_id"])
            self.audit.record(
                conn,
                project_id=project_id_for_audit,
                event_type="job_started",
                target_type="generation_job",
                target_id=str(job_id),
                payload={"job_type": job_type},
            )

        try:
            result = self.dispatcher.dispatch(job_type, payload)
        except Exception as exc:
            with self.db.connection() as conn:
                self.repo.mark_failed(conn, job_id, str(exc))
                self.audit.record(
                    conn,
                    project_id=project_id_for_audit,
                    event_type="job_failed",
                    target_type="generation_job",
                    target_id=str(job_id),
                    payload={"job_type": job_type, "error": str(exc)},
                )
            return JobRunResult(job_id=job_id, job_type=job_type, status=JobStatus.FAILED, error_message=str(exc))

        with self.db.connection() as conn:
            self.repo.mark_completed(conn, job_id, result)
            self.audit.record(
                conn,
                project_id=project_id_for_audit,
                event_type="job_completed",
                target_type="generation_job",
                target_id=str(job_id),
                payload={"job_type": job_type},
            )
        return JobRunResult(job_id=job_id, job_type=job_type, status=JobStatus.COMPLETED, result=result)

    def run_all(self, project_slug: str, *, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(200, int(limit)))
        results: list[dict[str, Any]] = []
        for _ in range(limit):
            result = self.run_next(project_slug)
            if result is None:
                break
            results.append(result.to_dict())
            if result.status == JobStatus.FAILED:
                break
        return {
            "project_slug": project_slug,
            "ran_count": len(results),
            "failed_count": sum(1 for item in results if item["status"] == JobStatus.FAILED.value),
            "results": results,
        }

    def retry(self, project_slug: str, job_id: int) -> dict[str, Any]:
        with self.db.connection() as conn:
            project = self.projects.get_project(project_slug, conn=conn)
            row = self.repo.get(conn, job_id)
            if int(row["project_id"]) != int(project["id"]):
                raise KeyError(f"Job {job_id} does not belong to project {project_slug}.")
            retried = self.repo.retry(conn, job_id)
            self.audit.record(
                conn,
                project_id=project["id"],
                event_type="job_retried",
                target_type="generation_job",
                target_id=str(job_id),
                payload={"job_type": retried["job_type"]},
            )
            return self._row_to_dict(retried)

    def requeue_stale_running(self, *, older_than_minutes: int = 60) -> dict[str, int]:
        with self.db.connection() as conn:
            count = self.repo.requeue_stale_running(conn, older_than_minutes=older_than_minutes)
            return {"requeued_count": count}

    def _row_to_dict(self, row: Row) -> dict[str, Any]:
        payload = {key: row[key] for key in row.keys()}
        for key in ("payload_json", "result_json"):
            try:
                payload[key[:-5] if key.endswith("_json") else key] = json.loads(row[key] or "{}")
            except json.JSONDecodeError:
                payload[key[:-5] if key.endswith("_json") else key] = {}
        return payload
