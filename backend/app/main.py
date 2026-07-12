from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.registry import AdapterRegistry
from app.models import (
    JobCreateRequest,
    JobView,
    LibraryMangaCreateRequest,
    LibraryMangaUpdateRequest,
    LibraryRootCreateRequest,
)
from app.services.job_runner import JobRunner
from app.services.library_scheduler import LibraryScheduler
from app.services.library_service import LibraryService
from app.services.library_store import LibraryStore
from app.storage.library_db import default_library_db_path
from app.storage.repository import InMemoryJobRepository

app = FastAPI(title="Manga Origin Getter", version="0.1.0")

repository = InMemoryJobRepository()
registry = AdapterRegistry()
data_dir = Path(__file__).resolve().parents[1] / "data" / "jobs"
data_dir.mkdir(parents=True, exist_ok=True)
runner = JobRunner(repository=repository, registry=registry, data_dir=data_dir)
library_store = LibraryStore(default_library_db_path())
library_service = LibraryService(library_store, registry, job_runner=runner)
library_scheduler = LibraryScheduler(library_service)


@app.on_event("startup")
async def on_startup() -> None:
    library_scheduler.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await library_scheduler.stop()


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


@app.get("/jobs", response_model=list[JobView])
async def list_jobs() -> list[JobView]:
    jobs = await repository.list()
    jobs.reverse()
    return [
        JobView(
            id=job.id,
            source_url=job.source_url,
            status=job.status,
            work_title=job.work_title,
            total_chapters=job.total_chapters,
            completed_chapters=job.completed_chapters,
            output_dir=job.output_dir,
            error=job.error,
        )
        for job in jobs
    ]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await repository.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()


@app.get("/settings/storage")
async def get_storage_settings() -> dict:
    jobs = await repository.list()
    stats = runner.storage_stats()
    return {
        "jobs_total": len(jobs),
        "jobs_failed": sum(1 for job in jobs if str(job.status) == "failed"),
        "jobs_done": sum(1 for job in jobs if str(job.status) == "done"),
        **stats,
    }


@app.get("/library/overview")
async def library_overview() -> dict:
    return library_service.list_library_overview()


@app.get("/library/mangas/{manga_id}")
async def library_manga_details(manga_id: int) -> dict:
    try:
        return library_service.get_manga_details(manga_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/library/roots")
async def list_library_roots() -> list[dict]:
    return library_service.list_library_roots()


@app.post("/library/roots")
async def add_library_root(request: LibraryRootCreateRequest) -> dict:
    try:
        return library_service.add_library_root(request.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/library/roots/{root_id}")
async def delete_library_root(root_id: int) -> dict:
    try:
        library_service.remove_library_root(root_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": True, "root_id": root_id}


@app.post("/library/mangas")
async def add_library_manga(request: LibraryMangaCreateRequest) -> dict:
    try:
        manga_id = library_service.add_or_update_tracked_manga(
            source_url=str(request.source_url),
            scan_interval_minutes=request.scan_interval_minutes,
            local_subdir=request.local_subdir,
            auto_download_missing=request.auto_download_missing,
            root_id=request.root_id,
        )
        return await library_manga_scan(manga_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/library/mangas/{manga_id}")
async def update_library_manga(manga_id: int, request: LibraryMangaUpdateRequest) -> dict:
    manga = library_store.get_manga(manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")
    library_store.update_manga_schedule(
        manga_id,
        scan_interval_minutes=request.scan_interval_minutes,
        auto_download_missing=request.auto_download_missing,
    )
    return library_service.get_manga_details(manga_id)


@app.post("/library/mangas/{manga_id}/scan")
async def library_manga_scan(manga_id: int) -> dict:
    try:
        return await library_service.scan_manga(manga_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/library/mangas/{manga_id}/download-missing")
async def library_download_missing(manga_id: int) -> dict:
    try:
        return await library_service.start_missing_chapters_job(manga_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/library/mangas/{manga_id}")
async def library_delete_manga(manga_id: int) -> dict:
    try:
        library_service.delete_manga(manga_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "manga_id": manga_id}


@app.post("/library/scan-all")
async def library_scan_all() -> dict:
    scanned = 0
    errors: list[dict] = []
    for manga in library_store.list_manga():
        manga_id = int(manga["id"])
        try:
            await library_service.scan_manga(manga_id)
            scanned += 1
        except Exception as exc:
            errors.append({"manga_id": manga_id, "error": str(exc)})
    return {"scanned": scanned, "errors": errors}


@app.post("/settings/purge")
async def purge_storage() -> dict:
    try:
        result = await runner.purge_all_job_data()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "message": "Application data purged",
        **result,
    }


@app.post("/jobs/{job_id}/retry-failed", response_model=JobView, status_code=202)
async def retry_failed_chapters(job_id: str) -> JobView:
    try:
        job = await runner.retry_failed_chapters(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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
