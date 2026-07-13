from __future__ import annotations

from typing import Any

import pytest
from pydantic import HttpUrl, ValidationError

from app.models import (
    JobCreateRequest,
    JobState,
    JobStatus,
    LibraryMangaCreateRequest,
)


def test_job_status_enum() -> None:
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.DISCOVERING.value == "discovering"
    assert JobStatus.DOWNLOADING.value == "downloading"
    assert JobStatus.ASSEMBLING.value == "assembling"
    assert JobStatus.DONE.value == "done"
    assert JobStatus.FAILED.value == "failed"


def test_job_create_request_valid() -> None:
    req = JobCreateRequest(source_url=HttpUrl("https://example.com/manga"))
    assert req.source_url == HttpUrl("https://example.com/manga")
    assert req.max_concurrency == 4
    assert req.output_dir is None


def test_job_create_request_invalid_concurrency() -> None:
    with pytest.raises(ValidationError):
        JobCreateRequest(
            source_url=HttpUrl("https://example.com/manga"),
            max_concurrency=13,
        )
    with pytest.raises(ValidationError):
        JobCreateRequest(
            source_url=HttpUrl("https://example.com/manga"),
            max_concurrency=0,
        )


def test_library_manga_create_request_defaults() -> None:
    req = LibraryMangaCreateRequest(source_url=HttpUrl("https://example.com/manga2"))
    assert req.source_url == HttpUrl("https://example.com/manga2")
    assert req.scan_interval_minutes == 60
    assert req.local_subdir is None
    assert req.auto_download_missing is False
    assert req.root_id is None


def test_job_state_model_dump() -> None:
    state = JobState(
        id="j1",
        source_url=HttpUrl("https://example.com/manga"),
    )
    data: dict[str, Any] = state.model_dump()
    assert data["id"] == "j1"
    assert data["status"] == "pending"
    assert data["total_chapters"] == 0
    assert data["completed_chapters"] == 0
    assert data["max_concurrency"] == 4
    assert data["chapter_artifacts"] == []
