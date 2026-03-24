from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from app.contracts.features import FeatureStorePort
from app.domain.identifiers import ModelId
from app.models import get_model_class


@dataclass
class TrainingRun:
    run_id: str
    model_id: str
    ticker: str
    status: str
    created_at: str
    updated_at: str
    error: str | None = None


class TrainingRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, TrainingRun] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def create_run(self, model_id: str, ticker: str) -> TrainingRun:
        run_id = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        now = datetime.now(tz=UTC).isoformat()
        run = TrainingRun(
            run_id=run_id,
            model_id=model_id,
            ticker=ticker,
            status="running",
            created_at=now,
            updated_at=now,
        )
        self._runs[run_id] = run
        return run

    def register_task(self, run_id: str, task: asyncio.Task[None]) -> None:
        self._tasks[run_id] = task

    def get(self, run_id: str) -> TrainingRun | None:
        return self._runs.get(run_id)

    def update(self, run_id: str, *, status: str, error: str | None = None) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        run.status = status
        run.error = error
        run.updated_at = datetime.now(tz=UTC).isoformat()


_registry = TrainingRegistry()


def get_training_registry() -> TrainingRegistry:
    return _registry


class TrainingService:
    """
    Lightweight training lifecycle manager.

    For now this validates model + feature availability and marks run completed.
    It is designed to be extended with full fit/persist pipeline.
    """

    def __init__(self, features: FeatureStorePort, registry: TrainingRegistry) -> None:
        self._features = features
        self._registry = registry

    async def start_training(self, model_id: ModelId, ticker: str) -> TrainingRun:
        sym = ticker.strip().upper()
        run = self._registry.create_run(model_id.value, sym)

        async def _job() -> None:
            try:
                # Minimal viability checks for training prerequisites.
                _ = get_model_class(model_id)()
                combined = await asyncio.to_thread(self._features.build_combined, sym)
                if combined.empty:
                    raise ValueError("combined features are empty")
                self._registry.update(run.run_id, status="completed")
            except Exception as e:  # noqa: BLE001
                self._registry.update(run.run_id, status="failed", error=str(e))

        task = asyncio.create_task(_job())
        self._registry.register_task(run.run_id, task)
        return run

    def get_status(self, run_id: str) -> TrainingRun | None:
        return self._registry.get(run_id)
