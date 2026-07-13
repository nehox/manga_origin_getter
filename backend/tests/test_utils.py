from __future__ import annotations

from datetime import datetime, timezone

from app.models import JobState, JobView
from app.services.utils import build_job_view, to_iso, utc_now, utcnow_iso
from tests.conftest import make_job_state


def test_utc_now() -> None:
    now = utc_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.tzinfo.utcoffset(now) == timezone.utc.utcoffset(now)


def test_to_iso() -> None:
    dt = datetime(2025, 6, 15, 14, 30, 0, 123456, tzinfo=timezone.utc)
    result = to_iso(dt)
    assert result == "2025-06-15T14:30:00+00:00"
    assert "." not in result


def test_utcnow_iso() -> None:
    result = utcnow_iso()
    assert result.endswith("+00:00")
    assert "." not in result

    now = utc_now()
    assert result == to_iso(now)  # noqa: E711


def test_build_job_view() -> None:
    job = make_job_state()
    view = build_job_view(job)
    assert isinstance(view, JobView)
    assert view.id == job.id
    assert view.source_url == job.source_url
    assert view.status == job.status
    assert view.work_title == job.work_title
    assert view.total_chapters == job.total_chapters
    assert view.completed_chapters == job.completed_chapters
    assert view.output_dir == job.output_dir
    assert view.error == job.error
