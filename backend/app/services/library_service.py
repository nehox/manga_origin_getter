from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from app.adapters.registry import AdapterRegistry
from app.services import logger
from app.services.downloader import download_images
from app.services.job_runner import JobRunner
from app.services.pdf_builder import build_pdf_from_images
from app.services.library_store import LibraryStore
from app.services.slug import to_slug
from app.services.utils import utc_now, to_iso


class LibraryService:
    def __init__(self, store: LibraryStore, registry: AdapterRegistry, job_runner: Optional[JobRunner] = None) -> None:
        self.store = store
        self.registry = registry
        self.job_runner = job_runner

    def list_library_roots(self) -> list[dict[str, Any]]:
        roots = self.store.list_roots()
        result = []
        for root in roots:
            path = Path(str(root["path"]))
            result.append(
                {
                    "id": int(root["id"]),
                    "path": str(root["path"]),
                    "exists": path.exists(),
                    "manga_count": self.store.count_manga_for_root(int(root["id"])),
                }
            )
        return result

    def add_library_root(self, root_path: str) -> dict[str, Any]:
        candidate = root_path.strip()
        if not candidate:
            raise ValueError("Le chemin de la racine ne peut pas etre vide")

        root = Path(candidate).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        root_id = self.store.add_root(str(root))
        return {"id": root_id, "path": str(root), "exists": True, "manga_count": 0}

    def remove_library_root(self, root_id: int) -> None:
        if not self.store.get_root(root_id):
            raise ValueError("Racine introuvable")
        if self.store.count_manga_for_root(root_id) > 0:
            raise ValueError("Impossible de supprimer une racine encore utilisee par des mangas")
        self.store.delete_root(root_id)

    def get_root_path(self, root_id: int) -> Path:
        root = self.store.get_root(root_id)
        if not root:
            raise ValueError("Racine introuvable")
        return Path(str(root["path"])).expanduser().resolve()

    def _default_root_id(self) -> Optional[int]:
        roots = self.store.list_roots()
        return int(roots[0]["id"]) if roots else None

    def _sanitize_local_subdir(self, local_subdir: str) -> str:
        candidate = local_subdir.strip()
        if not candidate:
            raise ValueError("Local subdir cannot be empty")

        path = Path(candidate)
        if path.is_absolute():
            raise ValueError("Local subdir must be a relative path")

        cleaned_parts: list[str] = []
        for part in path.parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise ValueError("Local subdir cannot contain '..'")
            cleaned_parts.append(part)

        if not cleaned_parts:
            raise ValueError("Local subdir cannot be empty")

        return str(Path(*cleaned_parts))

    def add_or_update_tracked_manga(
        self,
        *,
        source_url: str,
        scan_interval_minutes: int,
        local_subdir: Optional[str] = None,
        auto_download_missing: bool = False,
        root_id: Optional[int] = None,
    ) -> int:
        _ = self.registry.resolve(source_url)

        if root_id is None:
            root_id = self._default_root_id()
        if root_id is None:
            raise ValueError("Aucune racine de bibliotheque configuree. Ajoute une racine dans Parametres.")
        if not self.store.get_root(root_id):
            raise ValueError("Racine introuvable")

        parsed = urlparse(source_url)
        slug = Path(parsed.path.rstrip("/")).name
        title = slug.replace("-", " ").title() if slug else "Manga"
        if local_subdir and local_subdir.strip():
            subdir = self._sanitize_local_subdir(local_subdir)
        else:
            subdir = to_slug(title)
        return self.store.upsert_manga(
            title=title,
            slug=to_slug(title),
            source_url=source_url,
            local_subdir=subdir,
            scan_interval_minutes=scan_interval_minutes,
            auto_download_missing=auto_download_missing,
            root_id=root_id,
        )

    def delete_manga(self, manga_id: int) -> None:
        deleted = self.store.delete_manga(manga_id)
        if not deleted:
            raise ValueError("Manga not found")

    def _chapter_number_from_slug(self, chapter_slug: str) -> Optional[float]:
        token = chapter_slug.lower()
        token = token.replace("chapitre-", "").replace("chapter-", "")
        main = re.match(r"^(\d+)(?:-(\d+))?$", token)
        if main:
            base = float(main.group(1))
            decimal = main.group(2)
            if decimal:
                return float(f"{int(main.group(1))}.{int(decimal)}")
            return base
        generic = re.search(r"(\d+)", token)
        if generic:
            return float(generic.group(1))
        return None

    def _local_chapter_slugs(self, manga_dir: Path) -> set[str]:
        if not manga_dir.exists() or not manga_dir.is_dir():
            return set()
        slugs: set[str] = set()
        for file_path in manga_dir.glob("*.pdf"):
            slugs.add(file_path.stem.strip().lower())
        return slugs

    def _next_scan_iso(self, interval_minutes: int) -> str:
        return to_iso(utc_now() + timedelta(minutes=max(1, interval_minutes)))

    async def scan_manga(self, manga_id: int, *, force_download_missing: bool = False) -> dict[str, Any]:
        manga = self.store.get_manga(manga_id)
        if not manga:
            raise ValueError("Manga not found")

        root_id = manga.get("root_id")
        if root_id is None:
            raise RuntimeError("Aucune racine de bibliotheque associee a ce manga")
        root = self.get_root_path(int(root_id))

        source_url = str(manga["source_url"])
        adapter = self.registry.resolve(source_url)

        try:
            work_title, chapters = await adapter.discover_chapters(source_url)
            cover_url = await adapter.extract_cover_url(source_url)
            raw_categories = await adapter.extract_categories(source_url)
            categories_str = ",".join(raw_categories) if raw_categories else None
            local_subdir = str(manga["local_subdir"])
            local_dir = root / local_subdir
            local_slugs = self._local_chapter_slugs(local_dir)
            remote_by_slug = {chapter.slug: chapter for chapter in chapters}

            remote_slugs: set[str] = set()
            for chapter in chapters:
                remote_slugs.add(chapter.slug)
                self.store.upsert_chapter(
                    manga_id=manga_id,
                    chapter_url=chapter.url,
                    chapter_slug=chapter.slug,
                    chapter_title=chapter.title,
                    chapter_number=self._chapter_number_from_slug(chapter.slug),
                    remote_present=True,
                    local_present=chapter.slug in local_slugs,
                )

            self.store.mark_remote_missing_for_absent(manga_id, remote_slugs)

            missing_slugs = sorted(slug for slug in remote_slugs if slug not in local_slugs)
            should_download = force_download_missing or bool(int(manga.get("auto_download_missing") or 0))
            if should_download and missing_slugs:
                await self.download_missing_chapters(
                    manga_id,
                    chapter_slugs=missing_slugs,
                    remote_chapter_map=remote_by_slug,
                )

                # Refresh local presence after automatic downloads.
                local_slugs = self._local_chapter_slugs(local_dir)
                for chapter in chapters:
                    self.store.upsert_chapter(
                        manga_id=manga_id,
                        chapter_url=chapter.url,
                        chapter_slug=chapter.slug,
                        chapter_title=chapter.title,
                        chapter_number=self._chapter_number_from_slug(chapter.slug),
                        remote_present=True,
                        local_present=chapter.slug in local_slugs,
                    )

            self.store.upsert_manga(
                title=work_title,
                slug=to_slug(work_title),
                source_url=source_url,
                local_subdir=local_subdir,
                scan_interval_minutes=int(manga["scan_interval_minutes"]),
                auto_download_missing=bool(int(manga.get("auto_download_missing") or 0)),
                cover_url=cover_url,
                categories=categories_str,
            )

            self.store.mark_scan_result(
                manga_id,
                next_scan_at=self._next_scan_iso(int(manga["scan_interval_minutes"])),
                status="ok",
                error=None,
            )

            title = work_title or manga["title"]
            if missing_slugs:
                logger.info("scan", f"{title}: {len(missing_slugs)} nouveau(x) chapitre(s) trouve(s)")
            else:
                logger.info("scan", f"{title}: aucun nouveau chapitre")
        except Exception as exc:
            title = manga.get("title", f"#{manga_id}")
            logger.error("scan", f"{title}: erreur - {exc}")
            self.store.mark_scan_result(
                manga_id,
                next_scan_at=self._next_scan_iso(int(manga["scan_interval_minutes"])),
                status="error",
                error=str(exc),
            )
            raise

        return self.get_manga_details(manga_id)

    async def download_missing_chapters(
        self,
        manga_id: int,
        *,
        chapter_slugs: Optional[list[str]] = None,
        remote_chapter_map: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        manga = self.store.get_manga(manga_id)
        if not manga:
            raise ValueError("Manga not found")

        root_id = manga.get("root_id")
        if root_id is None:
            raise RuntimeError("Aucune racine de bibliotheque associee a ce manga")
        root = self.get_root_path(int(root_id))

        source_url = str(manga["source_url"])
        adapter = self.registry.resolve(source_url)
        local_subdir = str(manga["local_subdir"])
        local_dir = root / local_subdir
        local_dir.mkdir(parents=True, exist_ok=True)

        if remote_chapter_map is None:
            _, remote_chapters = await adapter.discover_chapters(source_url)
            remote_chapter_map = {chapter.slug: chapter for chapter in remote_chapters}

        if chapter_slugs is None:
            details = self.get_manga_details(manga_id)
            chapter_slugs = [chapter["chapter_slug"] for chapter in details["missing_chapters"]]

        downloaded = 0
        for chapter_slug in chapter_slugs:
            chapter = remote_chapter_map.get(chapter_slug)
            if not chapter:
                continue

            image_urls = await adapter.extract_image_urls(chapter.url)
            temp_dir = Path(__file__).resolve().parents[2] / "data" / "jobs" / "library-temp" / str(manga_id) / chapter_slug
            image_paths = await download_images(image_urls, temp_dir / "images", max_concurrency=4)
            output_pdf = local_dir / f"{chapter_slug}.pdf"
            build_pdf_from_images(image_paths, output_pdf)

            self.store.upsert_chapter(
                manga_id=manga_id,
                chapter_url=chapter.url,
                chapter_slug=chapter.slug,
                chapter_title=chapter.title,
                chapter_number=self._chapter_number_from_slug(chapter.slug),
                remote_present=True,
                local_present=True,
            )
            downloaded += 1

        details = self.get_manga_details(manga_id)
        details["downloaded_count"] = downloaded
        return details

    async def start_missing_chapters_job(self, manga_id: int) -> dict[str, Any]:
        """Launch a tracked background job to download this manga's missing chapters.

        Unlike ``download_missing_chapters`` (used internally by auto-scan), this
        creates a regular job entry so the download shows up in the Telechargements
        page/queue just like manual jobs.
        """
        if self.job_runner is None:
            raise RuntimeError("Le systeme de jobs n'est pas configure")

        manga = self.store.get_manga(manga_id)
        if not manga:
            raise ValueError("Manga not found")

        root_id = manga.get("root_id")
        if root_id is None:
            raise RuntimeError("Aucune racine de bibliotheque associee a ce manga")
        root = self.get_root_path(int(root_id))

        local_subdir = str(manga["local_subdir"])
        target_dir = root / local_subdir

        chapters = self.store.list_chapters(manga_id)
        missing = [
            chapter
            for chapter in chapters
            if int(chapter["remote_present"]) == 1 and int(chapter["local_present"]) == 0
        ]
        if not missing:
            raise ValueError("Aucun chapitre manquant a telecharger")

        missing_by_slug = {str(chapter["chapter_slug"]): chapter for chapter in missing}

        def on_chapter_done(chapter_slug: str) -> None:
            chapter = missing_by_slug.get(chapter_slug)
            if not chapter:
                return
            self.store.upsert_chapter(
                manga_id=manga_id,
                chapter_url=str(chapter["chapter_url"]),
                chapter_slug=chapter_slug,
                chapter_title=str(chapter["chapter_title"]),
                chapter_number=chapter["chapter_number"],
                remote_present=True,
                local_present=True,
            )

        job = await self.job_runner.create_tracked_download_job(
            source_url=str(manga["source_url"]),
            work_title=str(manga["title"]),
            target_dir=target_dir,
            chapters=[
                (str(chapter["chapter_title"]), str(chapter["chapter_slug"]), str(chapter["chapter_url"]))
                for chapter in missing
            ],
            max_concurrency=4,
            on_chapter_done=on_chapter_done,
        )
        return {"job_id": job.id, "missing_count": len(missing)}

    def list_unlinked_local_dirs(self) -> list[dict[str, Any]]:
        tracked = {
            (manga.get("root_id"), str(manga["local_subdir"]))
            for manga in self.store.list_manga()
        }
        unlinked: list[dict[str, Any]] = []
        for root_row in self.store.list_roots():
            root_id = int(root_row["id"])
            root = Path(str(root_row["path"])).expanduser().resolve()
            if not root.exists():
                continue
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                if (root_id, child.name) in tracked:
                    continue
                pdf_count = len(list(child.glob("*.pdf")))
                if pdf_count == 0:
                    continue
                unlinked.append(
                    {
                        "root_id": root_id,
                        "root_path": str(root),
                        "local_subdir": child.name,
                        "pdf_count": pdf_count,
                    }
                )
        return unlinked

    def get_manga_details(self, manga_id: int) -> dict[str, Any]:
        manga = self.store.get_manga(manga_id)
        if not manga:
            raise ValueError("Manga not found")

        chapters = self.store.list_chapters(manga_id)
        remote_present = [c for c in chapters if int(c["remote_present"]) == 1]
        local_present = [c for c in remote_present if int(c["local_present"]) == 1]
        missing = [c for c in remote_present if int(c["local_present"]) == 0]

        local_numbers = sorted({float(c["chapter_number"]) for c in local_present if c["chapter_number"] is not None})
        numeric_gaps: list[int] = []
        for i in range(len(local_numbers) - 1):
            current = int(local_numbers[i])
            nxt = int(local_numbers[i + 1])
            if nxt - current > 1:
                numeric_gaps.extend(list(range(current + 1, nxt)))

        def chapter_status(c: dict[str, Any]) -> str:
            if int(c["local_present"]) == 1:
                return "downloaded"
            if int(c["remote_present"]) == 1:
                return "missing"
            return "unavailable"

        root_id = manga.get("root_id")
        root_path: Optional[str] = None
        if root_id is not None:
            root_row = self.store.get_root(int(root_id))
            if root_row:
                root_path = str(root_row["path"])

        raw_categories = manga.get("categories")
        categories_list: list[str] = []
        if raw_categories and str(raw_categories).strip():
            categories_list = [c.strip() for c in str(raw_categories).split(",") if c.strip()]
        source_url = str(manga.get("source_url", ""))
        is_adult = "hentai-origines" in source_url

        return {
            **manga,
            "root_path": root_path,
            "auto_download_missing": bool(int(manga.get("auto_download_missing") or 0)),
            "categories": categories_list,
            "is_adult": is_adult,
            "remote_total": len(remote_present),
            "present_total": len(local_present),
            "missing_total": len(missing),
            "missing_chapters": [
                {
                    "chapter_slug": c["chapter_slug"],
                    "chapter_title": c["chapter_title"],
                    "chapter_url": c["chapter_url"],
                    "chapter_number": c["chapter_number"],
                }
                for c in missing
            ],
            "chapters": [
                {
                    "chapter_slug": c["chapter_slug"],
                    "chapter_title": c["chapter_title"],
                    "chapter_url": c["chapter_url"],
                    "chapter_number": c["chapter_number"],
                    "status": chapter_status(c),
                }
                for c in chapters
            ],
            "numeric_gaps": numeric_gaps,
        }

    def list_library_overview(self) -> dict[str, Any]:
        mangas = self.store.list_manga()
        with_stats = [self.get_manga_details(int(manga["id"])) for manga in mangas]
        return {
            "library_roots": self.list_library_roots(),
            "mangas": with_stats,
            "unlinked_dirs": self.list_unlinked_local_dirs(),
        }

    def due_manga_ids(self) -> list[int]:
        return self.store.list_due_manga_ids(to_iso(utc_now()))
