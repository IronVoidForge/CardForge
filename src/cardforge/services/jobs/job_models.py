from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cardforge.domain.enums import JobStatus, JobType


@dataclass(frozen=True)
class JobCreateRequest:
    project_id: int
    job_type: JobType
    target_type: str
    target_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    max_attempts: int = 3


@dataclass(frozen=True)
class JobRunResult:
    job_id: int
    job_type: str
    status: JobStatus
    result: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status.value,
            "result": self.result,
            "error_message": self.error_message,
        }
