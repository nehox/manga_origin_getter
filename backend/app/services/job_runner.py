from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.adapters.registry import AdapterRegistry
from app.models import ChapterArtifact, JobCreateRequest, JobState, JobStatus
from app.services.downloader import download_images
from app.services.pdf_builder import build_pdf_from_images
from app.services.slug import to_slug
from app.storage.repository import InMemoryJobRepository


class JobRunner:
    def __init__(self, repository: InMemoryJobRepository, registry: AdapterRegistry, data_dir: Path) -> None:
        self.repository = repository
        self.registry = registry
        self.data_dir = data_dir

    async def create_job(self, request: JobCreateRequest) -> JobState:
        output_dir = self._resolve_output_dir(request.output_dir)
        job = JobState(
            id=str(uuid4()),
            source_url=request.source_url,
            status=JobStatus.PENDING,
            output_dir=str(output_dir),
        )
        await self.repository.create(job)
        asyncio.create_task(self._run_job(job.id, str(request.source_url), request.max_concurrency))
        return job

    def _resolve_output_dir(self, output_dir: Optional[str]) -> Path:
        if output_dir and output_dir.strip():
            resolved = Path(output_dir).expanduser().resolve()
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved

        default_dir = self.data_dir / "exports"
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir

    def _job_pdf_dir(self, job: JobState) -> Path:
        root = Path(job.output_dir or (self.data_dir / "exports")).expanduser().resolve()
        work_folder = to_slug(job.work_title or "manga")
        pdf_dir = root / work_folder
        pdf_dir.mkdir(parents=True, exist_ok=True)
        return pdf_dir

    async def _run_job(self, job_id: str, source_url: str, max_concurrency: int) -> None:
        job = await self.repository.get(job_id)
        if not job:
            return

        try:
            adapter = self.registry.resolve(source_url)

            job.status = JobStatus.DISCOVERING
            await self.repository.update(job)

            work_title, chapters = await adapter.discover_chapters(source_url)
            if not chapters:
                raise RuntimeError("No chapters found from source URL")

            job.work_title = work_title
            job.total_chapters = len(chapters)
            job.chapter_artifacts = [
                ChapterArtifact(
                    title=chapter.title,
                    slug=chapter.slug,
                    source_url=chapter.url,
                    status=JobStatus.PENDING,
                )
                for chapter in chapters
            ]
            await self.repository.update(job)

            for chapter in chapters:
                await self._run_chapter(job_id, chapter.title, chapter.slug, chapter.url, max_concurrency)

            job = await self.repository.get(job_id)
            if not job:
                return
            if any(chapter.status == JobStatus.FAILED for chapter in job.chapter_artifacts):
                job.status = JobStatus.FAILED
                if not job.error:
                    job.error = "One or more chapters failed"
            else:
                job.status = JobStatus.DONE
            await self.repository.update(job)
        except Exception as exc:
            job = await self.repository.get(job_id)
            if not job:
                return
            job.status = JobStatus.FAILED
            job.error = str(exc)
            await self.repository.update(job)

    async def _run_chapter(
        self,
        job_id: str,
        chapter_title: str,
        chapter_slug: str,
        chapter_url: str,
        max_concurrency: int,
    ) -> None:
        job = await self.repository.get(job_id)
        if not job:
            return

        chapter = next((item for item in job.chapter_artifacts if item.slug == chapter_slug), None)
        if not chapter:
            return

        chapter.status = JobStatus.DOWNLOADING
        job.status = JobStatus.DOWNLOADING
        await self.repository.update(job)

        try:
            adapter = self.registry.resolve(str(job.source_url))
            image_urls = await adapter.extract_image_urls(chapter_url)

            chapter_dir = self.data_dir / job_id / chapter_slug
            image_dir = chapter_dir / "images"
            pdf_dir = self._job_pdf_dir(job)

            image_paths = await download_images(image_urls, image_dir, max_concurrency=max_concurrency)

            chapter.status = JobStatus.ASSEMBLING
            chapter.image_count = len(image_paths)
            job.status = JobStatus.ASSEMBLING
            await self.repository.update(job)

            pdf_path = pdf_dir / f"{chapter_slug}.pdf"
            build_pdf_from_images(image_paths, pdf_path)

            chapter.status = JobStatus.DONE
            chapter.pdf_path = str(pdf_path)
            job.completed_chapters = sum(1 for item in job.chapter_artifacts if item.status == JobStatus.DONE)
            await self.repository.update(job)
        except Exception as exc:
            chapter.status = JobStatus.FAILED
            chapter.error = str(exc)
            job.error = str(exc)
            await self.repository.update(job)
