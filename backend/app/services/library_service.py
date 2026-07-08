from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from app.adapters.registry import AdapterRegistry
from app.services.downloader import download_images
from app.services.pdf_builder import build_pdf_from_images
from app.services.library_store import LibraryStore
from app.services.slug import to_slug


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


class LibraryService:
    def __init__(self, store: LibraryStore, registry: AdapterRegistry) -> None:
        self.store = store
        self.registry = registry

    def get_library_root(self) -> Optional[Path]:
        root = self.store.get_setting("library_root_path")
        if not root:
            return None
        return Path(root).expanduser().resolve()

    def set_library_root(self, root_path: str) -> Path:
        root = Path(root_path).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.store.set_setting("library_root_path", str(root))
        return root

    def add_or_update_tracked_manga(
        self,
        *,
        source_url: str,
        scan_interval_minutes: int,
        local_subdir: Optional[str] = None,
        auto_download_missing: bool = False,
    ) -> int:
        _ = self.registry.resolve(source_url)
        parsed = urlparse(source_url)
        slug = Path(parsed.path.rstrip("/")).name
        title = slug.replace("-", " ").title() if slug else "Manga"
        subdir = local_subdir.strip() if local_subdir and local_subdir.strip() else to_slug(title)
        return self.store.upsert_manga(
            title=title,
            slug=to_slug(title),
            source_url=source_url,
            local_subdir=to_slug(subdir),
            scan_interval_minutes=scan_interval_minutes,
            auto_download_missing=auto_download_missing,
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

        root = self.get_library_root()
        if not root:
            raise RuntimeError("Library root path is not configured")

        source_url = str(manga["source_url"])
        adapter = self.registry.resolve(source_url)

        try:
            work_title, chapters = await adapter.discover_chapters(source_url)
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
            )

            self.store.mark_scan_result(
                manga_id,
                next_scan_at=self._next_scan_iso(int(manga["scan_interval_minutes"])),
                status="ok",
                error=None,
            )
        except Exception as exc:
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

        root = self.get_library_root()
        if not root:
            raise RuntimeError("Library root path is not configured")

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

    def list_unlinked_local_dirs(self) -> list[dict[str, Any]]:
        root = self.get_library_root()
        if not root or not root.exists():
            return []

        tracked = {str(manga["local_subdir"]) for manga in self.store.list_manga()}
        unlinked: list[dict[str, Any]] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if child.name in tracked:
                continue
            pdf_count = len(list(child.glob("*.pdf")))
            if pdf_count == 0:
                continue
            unlinked.append({"local_subdir": child.name, "pdf_count": pdf_count})
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

        return {
            **manga,
            "auto_download_missing": bool(int(manga.get("auto_download_missing") or 0)),
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
            "numeric_gaps": numeric_gaps,
        }

    def list_library_overview(self) -> dict[str, Any]:
        mangas = self.store.list_manga()
        with_stats = [self.get_manga_details(int(manga["id"])) for manga in mangas]
        root = self.get_library_root()
        return {
            "library_root_path": str(root) if root else None,
            "mangas": with_stats,
            "unlinked_dirs": self.list_unlinked_local_dirs(),
        }

    def due_manga_ids(self) -> list[int]:
        return self.store.list_due_manga_ids(to_iso(utc_now()))
