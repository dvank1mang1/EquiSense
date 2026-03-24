from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

import pandas as pd

from app.contracts.features import FeatureStorePort
from app.domain.identifiers import ModelId
from app.models import get_model_class
from app.services.lifecycle_store import LifecycleStore, ModelLifecycleState


@dataclass
class TrainingRun:
    run_id: str
    model_id: str
    ticker: str
    status: str
    created_at: str
    updated_at: str
    params: dict[str, Any] | None = None
    dataset_fingerprint: str | None = None
    artifact_path: str | None = None
    metrics: dict[str, Any] | None = None
    error: str | None = None


class TrainingRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, TrainingRun] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def create_run(
        self,
        model_id: str,
        ticker: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> TrainingRun:
        run_id = f"{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        now = datetime.now(tz=UTC).isoformat()
        run = TrainingRun(
            run_id=run_id,
            model_id=model_id,
            ticker=ticker,
            status="running",
            created_at=now,
            updated_at=now,
            params=params,
        )
        self._runs[run_id] = run
        return run

    def register_task(self, run_id: str, task: asyncio.Task[None]) -> None:
        self._tasks[run_id] = task

    def get(self, run_id: str) -> TrainingRun | None:
        return self._runs.get(run_id)

    def list_runs(
        self,
        *,
        model_id: str | None = None,
        ticker: str | None = None,
        limit: int = 20,
    ) -> list[TrainingRun]:
        runs = sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
        if model_id is not None:
            runs = [r for r in runs if r.model_id == model_id]
        if ticker is not None:
            runs = [r for r in runs if r.ticker == ticker]
        return runs[: max(1, min(limit, 200))]

    def update(
        self,
        run_id: str,
        *,
        status: str,
        dataset_fingerprint: str | None = None,
        artifact_path: str | None = None,
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        run.status = status
        run.dataset_fingerprint = dataset_fingerprint
        run.artifact_path = artifact_path
        run.metrics = metrics
        run.error = error
        run.updated_at = datetime.now(tz=UTC).isoformat()


_registry = TrainingRegistry()


def get_training_registry() -> TrainingRegistry:
    return _registry


class ModelLifecycleRegistry:
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


_lifecycle_registry = ModelLifecycleRegistry()


def get_lifecycle_registry() -> LifecycleStore:
    return _lifecycle_registry


class TrainingRunStore(Protocol):
    async def upsert(self, run: TrainingRun) -> None: ...

    async def get(self, run_id: str) -> TrainingRun | None: ...

    async def list_runs(
        self, *, model_id: str | None = None, ticker: str | None = None, limit: int = 20
    ) -> list[TrainingRun]: ...


class TrainingService:
    """
    Training lifecycle manager with in-process async execution.

    Current pipeline:
    - build combined features for ticker
    - construct binary target (next-day returns > 0)
    - chronological train/test split
    - fit model, evaluate on holdout, persist artifact
    """

    def __init__(
        self,
        features: FeatureStorePort,
        registry: TrainingRegistry,
        experiment_store: TrainingRunStore,
        lifecycle: LifecycleStore,
    ) -> None:
        self._features = features
        self._registry = registry
        self._experiment_store = experiment_store
        self._lifecycle = lifecycle

    async def start_training(self, model_id: ModelId, ticker: str) -> TrainingRun:
        sym = ticker.strip().upper()
        run = self._registry.create_run(
            model_id.value,
            sym,
            params={"target": "next_day_return_gt_0", "split": "time_80_20"},
        )
        await self._experiment_store.upsert(run)

        async def _job() -> None:
            try:
                combined = await asyncio.to_thread(self._features.build_combined, sym)
                if combined.empty:
                    raise ValueError("combined features are empty")
                dataset_fingerprint = _build_dataset_fingerprint(combined)

                model_cls = get_model_class(model_id)
                instance = model_cls()

                train_df, test_df = _prepare_training_frames(combined, instance.feature_set)
                if train_df.empty or test_df.empty:
                    raise ValueError("not enough rows for train/test split")

                x_train = train_df[instance.feature_set].fillna(0.0)
                y_train = train_df["target"]
                x_test = test_df[instance.feature_set].fillna(0.0)
                y_test = test_df["target"]

                await asyncio.to_thread(instance.train, x_train, y_train)
                metrics = await asyncio.to_thread(instance.evaluate, x_test, y_test)
                artifact_path = str(_artifact_path_for_run(model_id.value, run.run_id))
                await asyncio.to_thread(instance.save, artifact_path)
                metrics = {
                    "f1": float(metrics["f1"]),
                    "roc_auc": float(metrics["roc_auc"]),
                    "precision": float(metrics["precision"]),
                    "recall": float(metrics["recall"]),
                    "train_rows": int(len(train_df)),
                    "test_rows": int(len(test_df)),
                }
            except Exception as e:  # noqa: BLE001
                self._registry.update(run.run_id, status="failed", error=str(e))
                failed = self._registry.get(run.run_id)
                if failed is not None:
                    await self._experiment_store.upsert(failed)
            else:
                self._registry.update(
                    run.run_id,
                    status="completed",
                    dataset_fingerprint=dataset_fingerprint,
                    artifact_path=artifact_path,
                    metrics=metrics,
                )
                done = self._registry.get(run.run_id)
                if done is not None:
                    await self._experiment_store.upsert(done)

        task = asyncio.create_task(_job())
        self._registry.register_task(run.run_id, task)
        return run

    async def get_status(self, run_id: str) -> TrainingRun | None:
        run = self._registry.get(run_id)
        if run is not None:
            return run
        return await self._experiment_store.get(run_id)

    async def list_experiments(
        self,
        *,
        model_id: str | None = None,
        ticker: str | None = None,
        limit: int = 20,
    ) -> list[TrainingRun]:
        normalized_ticker = ticker.strip().upper() if ticker else None
        runs = self._registry.list_runs(model_id=model_id, ticker=normalized_ticker, limit=limit)
        if runs:
            return runs
        return await self._experiment_store.list_runs(
            model_id=model_id,
            ticker=normalized_ticker,
            limit=limit,
        )

    async def promote_champion(
        self, model_id: str, run_id: str, *, reason: str
    ) -> ModelLifecycleState:
        run = await self.get_status(run_id)
        if run is None:
            raise ValueError(f"unknown run id: {run_id}")
        if run.model_id != model_id:
            raise ValueError(f"run {run_id} does not belong to model {model_id}")
        if run.status != "completed":
            raise ValueError("only completed runs can be promoted")
        return await self._lifecycle.promote(model_id, run_id, reason=reason)

    async def get_lifecycle(self, model_id: str) -> ModelLifecycleState:
        return await self._lifecycle.state(model_id)

    async def list_lifecycles(self) -> list[ModelLifecycleState]:
        return await self._lifecycle.list_states()


def _prepare_training_frames(
    df: pd.DataFrame, feature_set: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "returns" not in df.columns:
        raise ValueError("combined frame must include 'returns' for target construction")
    if "date" in df.columns:
        work = df.sort_values("date").copy()
    else:
        work = df.copy()

    missing = [c for c in feature_set if c not in work.columns]
    if missing:
        raise ValueError(f"combined frame missing model features: {','.join(missing[:8])}")

    # target = 1 if next-day return positive, else 0
    work["target"] = (pd.to_numeric(work["returns"], errors="coerce").shift(-1) > 0.0).astype(
        "int64"
    )
    work = work.dropna(subset=feature_set)
    work = work.iloc[:-1].copy()  # drop last row with unknown next-day target
    if len(work) < 30:
        raise ValueError("need at least 30 rows for stable train/test split")

    split_idx = int(len(work) * 0.8)
    split_idx = max(10, min(split_idx, len(work) - 5))
    train_df = work.iloc[:split_idx].copy()
    test_df = work.iloc[split_idx:].copy()
    return train_df, test_df


def _build_dataset_fingerprint(df: pd.DataFrame) -> str:
    cols = sorted([str(c) for c in df.columns])
    payload: dict[str, Any] = {
        "rows": int(len(df)),
        "columns": cols,
    }
    if "date" in df.columns and not df.empty:
        dates = pd.to_datetime(df["date"], errors="coerce").dropna()
        if not dates.empty:
            payload["min_date"] = str(dates.min())
            payload["max_date"] = str(dates.max())
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def _artifact_path_for_run(model_id: str, run_id: str) -> str:
    from pathlib import Path

    from app.core.config import settings

    return str(Path(settings.model_dir) / model_id / run_id / "model.joblib")
