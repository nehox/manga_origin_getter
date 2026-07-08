from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class JobStatus(str, Enum):
    PENDING = "pending"
    DISCOVERING = "discovering"
    DOWNLOADING = "downloading"
    ASSEMBLING = "assembling"
    DONE = "done"
    FAILED = "failed"


class ChapterRef(BaseModel):
    title: str
    url: HttpUrl
    slug: str


class ChapterArtifact(BaseModel):
    title: str
    slug: str
    source_url: HttpUrl
    image_count: int = 0
    pdf_path: Optional[str] = None
    status: JobStatus = JobStatus.PENDING
    error: Optional[str] = None


class JobCreateRequest(BaseModel):
    source_url: HttpUrl
    max_concurrency: int = Field(default=4, ge=1, le=12)
    output_dir: Optional[str] = None


class JobState(BaseModel):
    id: str
    source_url: HttpUrl
    status: JobStatus = JobStatus.PENDING
    work_title: Optional[str] = None
    total_chapters: int = 0
    completed_chapters: int = 0
    max_concurrency: int = 4
    output_dir: Optional[str] = None
    error: Optional[str] = None
    chapter_artifacts: list[ChapterArtifact] = Field(default_factory=list)


class JobView(BaseModel):
    id: str
    source_url: HttpUrl
    status: JobStatus
    work_title: Optional[str]
    total_chapters: int
    completed_chapters: int
    output_dir: Optional[str]
    error: Optional[str]


class JobPaths(BaseModel):
    base_dir: Path
    images_dir: Path
    pdf_dir: Path


class LibrarySettingsRequest(BaseModel):
    library_root_path: str


class LibraryMangaCreateRequest(BaseModel):
    source_url: HttpUrl
    scan_interval_minutes: int = Field(default=60, ge=5, le=10080)
    local_subdir: Optional[str] = None
    auto_download_missing: bool = False


class LibraryMangaUpdateRequest(BaseModel):
    scan_interval_minutes: Optional[int] = Field(default=None, ge=5, le=10080)
    auto_download_missing: Optional[bool] = None
