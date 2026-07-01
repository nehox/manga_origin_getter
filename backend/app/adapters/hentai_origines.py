from __future__ import annotations

from urllib.parse import urlparse

from app.adapters.mangas_origines import MangasOriginesAdapter


class HentaiOriginesAdapter(MangasOriginesAdapter):
    host = "hentai-origines.com"

    def supports(self, source_url: str) -> bool:
        parsed = urlparse(source_url)
        return parsed.netloc.endswith(self.host)
