from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from app.adapters.mangas_origines import MangasOriginesAdapter


class HentaiOriginesAdapter(MangasOriginesAdapter):
    host = "hentai-origines.com"

    def supports(self, source_url: str) -> bool:
        parsed = urlparse(source_url)
        return parsed.netloc.endswith(self.host)

    async def extract_cover_url(self, source_url: str) -> Optional[str]:
        return None

    async def extract_categories(self, source_url: str) -> list[str]:
        return ["Adulte"]
