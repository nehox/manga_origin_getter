from __future__ import annotations

from app.adapters.base import SourceAdapter
from app.adapters.mangas_origines import MangasOriginesAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: list[SourceAdapter] = [
            MangasOriginesAdapter(),
        ]

    def resolve(self, source_url: str) -> SourceAdapter:
        for adapter in self._adapters:
            if adapter.supports(source_url):
                return adapter
        raise ValueError("No adapter registered for source URL domain")
