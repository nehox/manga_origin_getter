from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChapterDescriptor:
    title: str
    url: str
    slug: str


class SourceAdapter:
    def supports(self, source_url: str) -> bool:
        raise NotImplementedError

    async def discover_chapters(self, source_url: str) -> tuple[str, list[ChapterDescriptor]]:
        raise NotImplementedError

    async def extract_image_urls(self, chapter_url: str) -> list[str]:
        raise NotImplementedError

    async def extract_cover_url(self, source_url: str) -> Optional[str]:
        raise NotImplementedError

    async def extract_categories(self, source_url: str) -> list[str]:
        raise NotImplementedError
