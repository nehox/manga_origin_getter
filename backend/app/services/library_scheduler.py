from __future__ import annotations

import asyncio
from typing import Optional

from app.services.library_service import LibraryService


class LibraryScheduler:
    def __init__(self, library_service: LibraryService, tick_seconds: int = 30) -> None:
        self.library_service = library_service
        self.tick_seconds = max(10, tick_seconds)
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._locks: set[int] = set()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="library-scheduler")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                due_ids = self.library_service.due_manga_ids()
                for manga_id in due_ids:
                    if manga_id in self._locks:
                        continue
                    self._locks.add(manga_id)
                    try:
                        await self.library_service.scan_manga(manga_id)
                    except Exception:
                        pass
                    finally:
                        self._locks.discard(manga_id)
            finally:
                await asyncio.sleep(self.tick_seconds)
