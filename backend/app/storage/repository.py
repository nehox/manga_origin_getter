from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Optional

from app.models import JobState


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: JobState) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: str) -> Optional[JobState]:
        async with self._lock:
            current = self._jobs.get(job_id)
            return deepcopy(current) if current else None

    async def update(self, job: JobState) -> None:
        async with self._lock:
            self._jobs[job.id] = job
