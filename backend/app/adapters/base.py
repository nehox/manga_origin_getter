from __future__ import annotations

from dataclasses import dataclass


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
