from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.identifiers import ModelId


@dataclass
class ModelLifecycleState:
    model_id: str
    champion_run_id: str | None
    updated_at: str
    history: list[dict[str, str]]


class LifecycleStore(Protocol):
    async def state(self, model_id: str) -> ModelLifecycleState: ...

    async def promote(self, model_id: str, run_id: str, *, reason: str) -> ModelLifecycleState: ...

    async def list_states(self) -> list[ModelLifecycleState]: ...


class InMemoryLifecycleStore:
    def __init__(self) -> None:
        self._champions: dict[str, str] = {}
        self._history: dict[str, list[dict[str, str]]] = {}

    async def state(self, model_id: str) -> ModelLifecycleState:
        hist = self._history.get(model_id, [])
        updated_at = hist[-1]["at"] if hist else datetime.now(tz=UTC).isoformat()
        return ModelLifecycleState(
            model_id=model_id,
            champion_run_id=self._champions.get(model_id),
            updated_at=updated_at,
            history=list(hist),
        )

    async def promote(self, model_id: str, run_id: str, *, reason: str) -> ModelLifecycleState:
        now = datetime.now(tz=UTC).isoformat()
        previous = self._champions.get(model_id)
        self._champions[model_id] = run_id
        self._history.setdefault(model_id, []).append(
            {
                "at": now,
                "run_id": run_id,
                "reason": reason,
                "previous": previous or "",
            }
        )
        return await self.state(model_id)

    async def list_states(self) -> list[ModelLifecycleState]:
        return [await self.state(mid.value) for mid in ModelId]


class PostgresLifecycleStore:
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
                        CREATE TABLE IF NOT EXISTS model_lifecycle (
                            model_id TEXT PRIMARY KEY,
                            champion_run_id TEXT NULL,
                            updated_at TEXT NOT NULL
                        )
                        """
                    )
                )
                await conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS model_lifecycle_history (
                            id BIGSERIAL PRIMARY KEY,
                            model_id TEXT NOT NULL,
                            run_id TEXT NOT NULL,
                            reason TEXT NOT NULL,
                            previous_run_id TEXT NULL,
                            at TEXT NOT NULL
                        )
                        """
                    )
                )
            self._is_ready = True

    async def _state_async(self, model_id: str) -> ModelLifecycleState:
        await self._ensure_schema()
        async with self._engine.begin() as conn:
            current = await conn.execute(
                text(
                    """
                    SELECT champion_run_id, updated_at
                    FROM model_lifecycle
                    WHERE model_id = :model_id
                    """
                ),
                {"model_id": model_id},
            )
            row = current.mappings().first()
            hist_result = await conn.execute(
                text(
                    """
                    SELECT at, run_id, reason, previous_run_id
                    FROM model_lifecycle_history
                    WHERE model_id = :model_id
                    ORDER BY id ASC
                    """
                ),
                {"model_id": model_id},
            )
            hist_rows = hist_result.mappings().all()

        history = [
            {
                "at": str(h["at"]),
                "run_id": str(h["run_id"]),
                "reason": str(h["reason"]),
                "previous": str(h["previous_run_id"] or ""),
            }
            for h in hist_rows
        ]
        updated_at = str(row["updated_at"]) if row else datetime.now(tz=UTC).isoformat()
        champion_run_id = str(row["champion_run_id"]) if row and row["champion_run_id"] else None
        return ModelLifecycleState(
            model_id=model_id,
            champion_run_id=champion_run_id,
            updated_at=updated_at,
            history=history,
        )

    async def _promote_async(
        self, model_id: str, run_id: str, *, reason: str
    ) -> ModelLifecycleState:
        await self._ensure_schema()
        now = datetime.now(tz=UTC).isoformat()
        async with self._engine.begin() as conn:
            current = await conn.execute(
                text("SELECT champion_run_id FROM model_lifecycle WHERE model_id = :model_id"),
                {"model_id": model_id},
            )
            row = current.mappings().first()
            previous = str(row["champion_run_id"]) if row and row["champion_run_id"] else None
            await conn.execute(
                text(
                    """
                    INSERT INTO model_lifecycle (model_id, champion_run_id, updated_at)
                    VALUES (:model_id, :run_id, :updated_at)
                    ON CONFLICT (model_id) DO UPDATE SET
                        champion_run_id = EXCLUDED.champion_run_id,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {"model_id": model_id, "run_id": run_id, "updated_at": now},
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO model_lifecycle_history (
                        model_id, run_id, reason, previous_run_id, at
                    ) VALUES (
                        :model_id, :run_id, :reason, :previous_run_id, :at
                    )
                    """
                ),
                {
                    "model_id": model_id,
                    "run_id": run_id,
                    "reason": reason,
                    "previous_run_id": previous,
                    "at": now,
                },
            )
        return await self._state_async(model_id)

    async def _list_states_async(self) -> list[ModelLifecycleState]:
        states: list[ModelLifecycleState] = []
        for mid in ModelId:
            states.append(await self._state_async(mid.value))
        return states

    async def state(self, model_id: str) -> ModelLifecycleState:
        return await self._state_async(model_id)

    async def promote(self, model_id: str, run_id: str, *, reason: str) -> ModelLifecycleState:
        return await self._promote_async(model_id, run_id, reason=reason)

    async def list_states(self) -> list[ModelLifecycleState]:
        return await self._list_states_async()


class ResilientLifecycleStore:
    def __init__(self, primary: LifecycleStore, fallback: LifecycleStore) -> None:
        self._primary = primary
        self._fallback = fallback

    async def state(self, model_id: str) -> ModelLifecycleState:
        try:
            return await self._primary.state(model_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("Lifecycle state failed in primary store: {}", e)
            return await self._fallback.state(model_id)

    async def promote(self, model_id: str, run_id: str, *, reason: str) -> ModelLifecycleState:
        state = await self._fallback.promote(model_id, run_id, reason=reason)
        try:
            return await self._primary.promote(model_id, run_id, reason=reason)
        except Exception as e:  # noqa: BLE001
            logger.warning("Lifecycle promote failed in primary store: {}", e)
            return state

    async def list_states(self) -> list[ModelLifecycleState]:
        try:
            return await self._primary.list_states()
        except Exception as e:  # noqa: BLE001
            logger.warning("Lifecycle list failed in primary store: {}", e)
            return await self._fallback.list_states()
