from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Protocol

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.services.training_service import TrainingRun


class ExperimentStore(Protocol):
    async def upsert(self, run: TrainingRun) -> None: ...

    async def get(self, run_id: str) -> TrainingRun | None: ...

    async def list_runs(
        self, *, model_id: str | None = None, ticker: str | None = None, limit: int = 20
    ) -> list[TrainingRun]: ...


class InMemoryExperimentStore:
    def __init__(self) -> None:
        self._runs: dict[str, TrainingRun] = {}

    async def upsert(self, run: TrainingRun) -> None:
        self._runs[run.run_id] = run

    async def get(self, run_id: str) -> TrainingRun | None:
        return self._runs.get(run_id)

    async def list_runs(
        self, *, model_id: str | None = None, ticker: str | None = None, limit: int = 20
    ) -> list[TrainingRun]:
        runs = sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
        if model_id:
            runs = [r for r in runs if r.model_id == model_id]
        if ticker:
            runs = [r for r in runs if r.ticker == ticker]
        return runs[: max(1, min(limit, 200))]


class PostgresExperimentStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._is_ready = False
        self._init_lock = asyncio.Lock()

    async def _ensure_schema(self) -> None:
        if self._is_ready:
            return
        async with self._init_lock:
            if self._is_ready:
                return
            async with self._engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS training_experiments (
                            run_id TEXT PRIMARY KEY,
                            model_id TEXT NOT NULL,
                            ticker TEXT NOT NULL,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            params_json TEXT NULL,
                            dataset_fingerprint TEXT NULL,
                            metrics_json TEXT NULL,
                            error TEXT NULL
                        )
                        """
                    )
                )
            self._is_ready = True

    async def upsert(self, run: TrainingRun) -> None:
        await self._ensure_schema()
        payload = asdict(run)
        params_json = json.dumps(payload["params"]) if payload["params"] is not None else None
        metrics_json = json.dumps(payload["metrics"]) if payload["metrics"] is not None else None
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO training_experiments (
                        run_id, model_id, ticker, status, created_at, updated_at,
                        params_json, dataset_fingerprint, metrics_json, error
                    ) VALUES (
                        :run_id, :model_id, :ticker, :status, :created_at, :updated_at,
                        :params_json, :dataset_fingerprint, :metrics_json, :error
                    )
                    ON CONFLICT (run_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at,
                        params_json = EXCLUDED.params_json,
                        dataset_fingerprint = EXCLUDED.dataset_fingerprint,
                        metrics_json = EXCLUDED.metrics_json,
                        error = EXCLUDED.error
                    """
                ),
                {
                    "run_id": run.run_id,
                    "model_id": run.model_id,
                    "ticker": run.ticker,
                    "status": run.status,
                    "created_at": run.created_at,
                    "updated_at": run.updated_at,
                    "params_json": params_json,
                    "dataset_fingerprint": run.dataset_fingerprint,
                    "metrics_json": metrics_json,
                    "error": run.error,
                },
            )

    async def get(self, run_id: str) -> TrainingRun | None:
        await self._ensure_schema()
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT run_id, model_id, ticker, status, created_at, updated_at,
                           params_json, dataset_fingerprint, metrics_json, error
                    FROM training_experiments
                    WHERE run_id = :run_id
                    """
                ),
                {"run_id": run_id},
            )
            row = result.mappings().first()
        if row is None:
            return None
        return TrainingRun(
            run_id=str(row["run_id"]),
            model_id=str(row["model_id"]),
            ticker=str(row["ticker"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            params=json.loads(str(row["params_json"])) if row["params_json"] else None,
            dataset_fingerprint=str(row["dataset_fingerprint"])
            if row["dataset_fingerprint"]
            else None,
            metrics=json.loads(str(row["metrics_json"])) if row["metrics_json"] else None,
            error=str(row["error"]) if row["error"] else None,
        )

    async def list_runs(
        self, *, model_id: str | None = None, ticker: str | None = None, limit: int = 20
    ) -> list[TrainingRun]:
        await self._ensure_schema()
        limit = max(1, min(limit, 200))
        where_parts: list[str] = []
        params: dict[str, object] = {"limit": limit}
        if model_id:
            where_parts.append("model_id = :model_id")
            params["model_id"] = model_id
        if ticker:
            where_parts.append("ticker = :ticker")
            params["ticker"] = ticker
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        query = f"""
            SELECT run_id, model_id, ticker, status, created_at, updated_at,
                   params_json, dataset_fingerprint, metrics_json, error
            FROM training_experiments
            {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(text(query), params)
            rows = result.mappings().all()
        runs: list[TrainingRun] = []
        for row in rows:
            runs.append(
                TrainingRun(
                    run_id=str(row["run_id"]),
                    model_id=str(row["model_id"]),
                    ticker=str(row["ticker"]),
                    status=str(row["status"]),
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"]),
                    params=json.loads(str(row["params_json"])) if row["params_json"] else None,
                    dataset_fingerprint=str(row["dataset_fingerprint"])
                    if row["dataset_fingerprint"]
                    else None,
                    metrics=json.loads(str(row["metrics_json"])) if row["metrics_json"] else None,
                    error=str(row["error"]) if row["error"] else None,
                )
            )
        return runs


class ResilientExperimentStore:
    """
    Postgres-backed store with graceful fallback to memory.
    """

    def __init__(self, primary: ExperimentStore, fallback: ExperimentStore) -> None:
        self._primary = primary
        self._fallback = fallback

    async def upsert(self, run: TrainingRun) -> None:
        await self._fallback.upsert(run)
        try:
            await self._primary.upsert(run)
        except Exception as e:  # noqa: BLE001
            logger.warning("Experiment upsert failed in primary store: {}", e)

    async def get(self, run_id: str) -> TrainingRun | None:
        run = await self._fallback.get(run_id)
        if run is not None:
            return run
        try:
            return await self._primary.get(run_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("Experiment get failed in primary store: {}", e)
            return None

    async def list_runs(
        self, *, model_id: str | None = None, ticker: str | None = None, limit: int = 20
    ) -> list[TrainingRun]:
        runs = await self._fallback.list_runs(model_id=model_id, ticker=ticker, limit=limit)
        if runs:
            return runs
        try:
            return await self._primary.list_runs(model_id=model_id, ticker=ticker, limit=limit)
        except Exception as e:  # noqa: BLE001
            logger.warning("Experiment list failed in primary store: {}", e)
            return []
