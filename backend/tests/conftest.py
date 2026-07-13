from __future__ import annotations

from pydantic import HttpUrl

from app.models import (
    ChapterArtifact,
    ChapterRef,
    JobState,
    JobStatus,
)


def make_job_state(**overrides: object) -> JobState:
    defaults: dict = {
        "id": "job-123",
        "source_url": HttpUrl("https://example.com/manga"),
        "status": JobStatus.PENDING,
        "work_title": "Test Manga",
        "total_chapters": 10,
        "completed_chapters": 3,
        "max_concurrency": 4,
        "output_dir": "/tmp/output",
        "error": None,
        "chapter_artifacts": [
            ChapterArtifact(
                title="Chapter 1",
                slug="chapter-1",
                source_url=HttpUrl("https://example.com/manga/1"),
            ),
        ],
    }
    defaults.update(overrides)
    return JobState(**defaults)


def make_chapter_ref(**overrides: object) -> ChapterRef:
    defaults: dict = {
        "title": "Chapter 1",
        "url": HttpUrl("https://example.com/manga/1"),
        "slug": "chapter-1",
    }
    defaults.update(overrides)
    return ChapterRef(**defaults)
