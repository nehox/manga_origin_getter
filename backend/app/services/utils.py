from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from app.models import JobState, JobView


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def utcnow_iso() -> str:
    return to_iso(utc_now())


def build_job_view(job: JobState) -> JobView:
    return JobView(
        id=job.id,
        source_url=job.source_url,
        status=job.status,
        work_title=job.work_title,
        total_chapters=job.total_chapters,
        completed_chapters=job.completed_chapters,
        output_dir=job.output_dir,
        error=job.error,
    )
