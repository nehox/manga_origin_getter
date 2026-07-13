from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.services import logger
from app.services.job_runner import JobRunner
from app.services.library_store import LibraryStore
from app.services.utils import utcnow_iso


class PurgeScheduler:
    def __init__(
        self,
        library_store: LibraryStore,
        job_runner: JobRunner,
        tick_seconds: int = 60,
    ) -> None:
        self.store = library_store
        self.runner = job_runner
        self.tick_seconds = max(10, tick_seconds)
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="purge-scheduler")

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
                enabled = self.store.get_setting("auto_purge_enabled")
                if enabled == "true":
                    interval_h = int(self.store.get_setting("auto_purge_interval_hours") or "24")
                    last_raw = self.store.get_setting("auto_purge_last_run")
                    now = datetime.now(timezone.utc)
                    if last_raw is None:
                        self.store.set_setting("auto_purge_last_run", utcnow_iso())
                    else:
                        last = datetime.fromisoformat(last_raw)
                        elapsed_h = (now - last).total_seconds() / 3600
                        if elapsed_h >= interval_h:
                            try:
                                result = await self.runner.purge_all_job_data()
                                self.store.set_setting("auto_purge_last_run", utcnow_iso())
                                logger.info("purge", f"Purge auto terminee: {result.get('removed_entries', 0)} entrees, {result.get('freed_bytes', 0)} octets liberes")
                            except RuntimeError:
                                logger.warn("purge", "Purge auto sautee: jobs en cours")
            except Exception:
                pass
            finally:
                await asyncio.sleep(self.tick_seconds)
