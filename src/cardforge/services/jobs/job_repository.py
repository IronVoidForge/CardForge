from __future__ import annotations

import json
from sqlite3 import Connection, Row
from typing import Any

from cardforge.domain.enums import JobStatus
from cardforge.services.jobs.job_models import JobCreateRequest


class JobRepository:
    """Small SQL boundary for generation_jobs state transitions."""

    def create(self, conn: Connection, request: JobCreateRequest) -> Row:
        conn.execute(
            """
            INSERT INTO generation_jobs(
              project_id, job_type, target_type, target_id, status, priority,
              max_attempts, payload_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.project_id,
                request.job_type.value,
                request.target_type,
                request.target_id,
                JobStatus.PENDING.value,
                request.priority,
                max(1, request.max_attempts),
                json.dumps(request.payload, ensure_ascii=False),
            ),
        )
        job_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        return self.get(conn, job_id)

    def get(self, conn: Connection, job_id: int) -> Row:
        row = conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return row

    def list_for_project(
        self,
        conn: Connection,
        project_id: int,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Row]:
        limit = max(1, min(500, int(limit)))
        if status:
            return list(
                conn.execute(
                    """
                    SELECT * FROM generation_jobs
                    WHERE project_id = ? AND status = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (project_id, status, limit),
                )
            )
        return list(
            conn.execute(
                """
                SELECT * FROM generation_jobs
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (project_id, limit),
            )
        )

    def next_pending(self, conn: Connection, project_id: int | None = None) -> Row | None:
        params: tuple[Any, ...]
        where = "status = ? AND attempt_count < max_attempts"
        params = (JobStatus.PENDING.value,)
        if project_id is not None:
            where += " AND project_id = ?"
            params = (JobStatus.PENDING.value, project_id)
        return conn.execute(
            f"""
            SELECT * FROM generation_jobs
            WHERE {where}
            ORDER BY priority ASC, created_at ASC, id ASC
            LIMIT 1
            """,
            params,
        ).fetchone()

    def mark_running(self, conn: Connection, job_id: int) -> Row:
        conn.execute(
            """
            UPDATE generation_jobs
            SET status = ?, attempt_count = attempt_count + 1, started_at = CURRENT_TIMESTAMP,
                error_message = '', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = ? AND attempt_count < max_attempts
            """,
            (JobStatus.RUNNING.value, job_id, JobStatus.PENDING.value),
        )
        row = self.get(conn, job_id)
        if row["status"] != JobStatus.RUNNING.value:
            raise RuntimeError(f"Job {job_id} could not be leased for running.")
        return row

    def mark_completed(self, conn: Connection, job_id: int, result: dict[str, Any]) -> Row:
        conn.execute(
            """
            UPDATE generation_jobs
            SET status = ?, result_json = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (JobStatus.COMPLETED.value, json.dumps(result, ensure_ascii=False), job_id),
        )
        return self.get(conn, job_id)

    def mark_failed(self, conn: Connection, job_id: int, error_message: str) -> Row:
        conn.execute(
            """
            UPDATE generation_jobs
            SET status = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (JobStatus.FAILED.value, error_message, job_id),
        )
        return self.get(conn, job_id)

    def retry(self, conn: Connection, job_id: int) -> Row:
        row = self.get(conn, job_id)
        if row["status"] not in {JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
            raise ValueError("Only failed or cancelled jobs can be retried.")
        if int(row["attempt_count"] or 0) >= int(row["max_attempts"] or 1):
            raise ValueError("Job has reached max attempts; increase max_attempts before retrying.")
        conn.execute(
            """
            UPDATE generation_jobs
            SET status = ?, error_message = '', completed_at = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (JobStatus.PENDING.value, job_id),
        )
        return self.get(conn, job_id)

    def cancel(self, conn: Connection, job_id: int, *, reason: str = "cancelled") -> Row:
        row = self.get(conn, job_id)
        if row["status"] == JobStatus.RUNNING.value:
            raise ValueError("Running jobs cannot be cancelled from this local queue; wait for failure or completion.")
        conn.execute(
            """
            UPDATE generation_jobs
            SET status = ?, error_message = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (JobStatus.CANCELLED.value, reason, job_id),
        )
        return self.get(conn, job_id)

    def requeue_stale_running(self, conn: Connection, *, older_than_minutes: int = 60) -> int:
        """Move stale running jobs back to pending if their process likely died."""
        older_than_minutes = max(1, int(older_than_minutes))
        cursor = conn.execute(
            """
            UPDATE generation_jobs
            SET status = ?, error_message = 'Requeued stale running job.', updated_at = CURRENT_TIMESTAMP
            WHERE status = ?
              AND started_at IS NOT NULL
              AND datetime(started_at, '+' || ? || ' minutes') < CURRENT_TIMESTAMP
              AND attempt_count < max_attempts
            """,
            (JobStatus.PENDING.value, JobStatus.RUNNING.value, older_than_minutes),
        )
        return int(cursor.rowcount or 0)
