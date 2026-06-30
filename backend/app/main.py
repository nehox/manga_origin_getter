from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.registry import AdapterRegistry
from app.models import JobCreateRequest, JobView
from app.services.job_runner import JobRunner
from app.storage.repository import InMemoryJobRepository

app = FastAPI(title="Manga Origin Getter", version="0.1.0")

repository = InMemoryJobRepository()
registry = AdapterRegistry()
data_dir = Path(__file__).resolve().parents[1] / "data" / "jobs"
data_dir.mkdir(parents=True, exist_ok=True)
runner = JobRunner(repository=repository, registry=registry, data_dir=data_dir)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobView, status_code=202)
async def create_job(request: JobCreateRequest) -> JobView:
    job = await runner.create_job(request)
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


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await repository.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()


@app.get("/jobs/{job_id}/chapters/{chapter_slug}/pdf")
async def download_chapter_pdf(job_id: str, chapter_slug: str) -> FileResponse:
    job = await repository.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    chapter = next((item for item in job.chapter_artifacts if item.slug == chapter_slug), None)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if not chapter.pdf_path:
        raise HTTPException(status_code=409, detail="PDF not available yet")

    file_path = Path(chapter.pdf_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF file is missing")

    return FileResponse(path=file_path, filename=file_path.name, media_type="application/pdf")


static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
