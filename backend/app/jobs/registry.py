from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class JobHandle:
    run_id: str
    task: asyncio.Task[tuple[str, str]]

    @property
    def status(self) -> str:
        if self.task.cancelled():
            return "cancelled"
        if self.task.done():
            return "failed" if self.task.exception() is not None else "completed"
        return "running"


class InMemoryJobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobHandle] = {}

    def register(self, run_id: str, task: asyncio.Task[tuple[str, str]]) -> None:
        self._jobs[run_id] = JobHandle(run_id=run_id, task=task)

    def get(self, run_id: str) -> JobHandle | None:
        return self._jobs.get(run_id)


_registry = InMemoryJobRegistry()


def get_job_registry() -> InMemoryJobRegistry:
    return _registry
