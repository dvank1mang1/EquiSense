from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

import pandas as pd
from loguru import logger

from app.contracts.features import FeatureStorePort
from app.core.config import get_settings
from app.domain.identifiers import ModelId
from app.ml.training_pipeline import calibrate_production_model, fit_production_pipeline
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


@dataclass
class PromotionDecision:
    accepted: bool
    reason: str
    candidate_run_id: str
    champion_before_run_id: str | None = None
    checks: dict[str, Any] | None = None


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
    - chronological train / validation / test (70/15/15)
    - fit on train (median imputer + class balance), isotonic calibration on val, evaluate on test
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
        settings = get_settings()
        run = self._registry.create_run(
            model_id.value,
            sym,
            params={
                "target": "next_day_return_gt_0",
                "split": "time_series",
                "train_fraction": settings.training_split_train_fraction,
                "val_end_fraction": settings.training_split_val_end_fraction,
                "min_rows": settings.training_min_rows,
                "imputation": "median_train",
                "class_balance": "scale_pos_weight_or_balanced",
                "calibration": "isotonic_prefit_on_val",
                "calibration_min_val_samples": settings.training_calibration_min_val_samples,
            },
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

                train_df, val_df, test_df = _prepare_training_frames(
                    combined,
                    instance.feature_set,
                    train_fraction=settings.training_split_train_fraction,
                    val_end_fraction=settings.training_split_val_end_fraction,
                    min_rows=settings.training_min_rows,
                )
                if train_df.empty or val_df.empty or test_df.empty:
                    raise ValueError("not enough rows for train/validation/test split")

                x_train = train_df[instance.feature_set]
                y_train = train_df["target"]
                x_val = val_df[instance.feature_set]
                y_val = val_df["target"]
                x_test = test_df[instance.feature_set]
                y_test = test_df["target"]

                await asyncio.to_thread(fit_production_pipeline, instance, x_train, y_train)
                calibration_status = await asyncio.to_thread(
                    calibrate_production_model,
                    instance,
                    x_val,
                    y_val,
                    min_samples=settings.training_calibration_min_val_samples,
                )
                metrics = await asyncio.to_thread(instance.evaluate, x_test, y_test)
                artifact_path = str(_artifact_path_for_run(model_id.value, run.run_id))
                await asyncio.to_thread(instance.save, artifact_path)
                metrics = {
                    "f1": float(metrics["f1"]),
                    "roc_auc": float(metrics["roc_auc"]),
                    "pr_auc": float(metrics["pr_auc"]),
                    "brier": float(metrics["brier"]),
                    "precision": float(metrics["precision"]),
                    "recall": float(metrics["recall"]),
                    "train_rows": int(len(train_df)),
                    "val_rows": int(len(val_df)),
                    "test_rows": int(len(test_df)),
                    "calibration": calibration_status,
                    "calibration_isotonic": calibration_status == "isotonic_applied",
                }
                if "date" in train_df.columns and not train_df.empty and not val_df.empty:
                    metrics["train_date_max"] = str(
                        pd.to_datetime(train_df["date"], errors="coerce").max().date()
                    )
                    metrics["val_date_min"] = str(
                        pd.to_datetime(val_df["date"], errors="coerce").min().date()
                    )
                    metrics["val_date_max"] = str(
                        pd.to_datetime(val_df["date"], errors="coerce").max().date()
                    )
                if "date" in test_df.columns and not test_df.empty:
                    metrics["test_date_min"] = str(
                        pd.to_datetime(test_df["date"], errors="coerce").min().date()
                    )
                logger.info(
                    "training completed run_id={} model={} ticker={} calibration={} roc_auc={:.4f}",
                    run.run_id,
                    model_id.value,
                    sym,
                    metrics.get("calibration"),
                    float(metrics["roc_auc"]),
                )
            except Exception as e:
                logger.exception(
                    "training failed run_id={} model={} ticker={}: {}",
                    run.run_id,
                    model_id.value,
                    sym,
                    e,
                )
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
        self, model_id: str, run_id: str, *, reason: str, force: bool = False
    ) -> tuple[ModelLifecycleState, PromotionDecision]:
        run = await self.get_status(run_id)
        if run is None:
            raise ValueError(f"unknown run id: {run_id}")
        if run.model_id != model_id:
            raise ValueError(f"run {run_id} does not belong to model {model_id}")
        if run.status != "completed":
            raise ValueError("only completed runs can be promoted")
        decision = await self.evaluate_promotion(model_id, run_id)
        if force and not decision.accepted:
            decision = PromotionDecision(
                accepted=True,
                reason=f"forced promotion: {reason}",
                candidate_run_id=run_id,
                champion_before_run_id=decision.champion_before_run_id,
                checks={**(decision.checks or {}), "forced": True},
            )
        if decision.accepted:
            state = await self._lifecycle.promote(model_id, run_id, reason=reason)
        else:
            state = await self._lifecycle.state(model_id)
        await self._persist_promotion_decision(run_id, decision)
        return state, decision

    async def get_lifecycle(self, model_id: str) -> ModelLifecycleState:
        return await self._lifecycle.state(model_id)

    async def list_lifecycles(self) -> list[ModelLifecycleState]:
        return await self._lifecycle.list_states()

    async def evaluate_promotion(self, model_id: str, run_id: str) -> PromotionDecision:
        settings = get_settings()
        candidate = await self.get_status(run_id)
        if candidate is None or candidate.metrics is None:
            return PromotionDecision(
                accepted=False,
                reason="candidate run has no metrics",
                candidate_run_id=run_id,
                checks={},
            )
        current = await self._lifecycle.state(model_id)
        champion_run_id = current.champion_run_id
        if champion_run_id is None:
            return PromotionDecision(
                accepted=True,
                reason="no current champion; accept first completed run",
                candidate_run_id=run_id,
                champion_before_run_id=None,
                checks={"bootstrap": True},
            )
        champion = await self.get_status(champion_run_id)
        if champion is None or champion.metrics is None:
            return PromotionDecision(
                accepted=True,
                reason="current champion metrics unavailable; accept candidate",
                candidate_run_id=run_id,
                champion_before_run_id=champion_run_id,
                checks={"champion_metrics_missing": True},
            )
        c_roc = _metric(candidate.metrics, "roc_auc")
        p_roc = _metric(champion.metrics, "roc_auc")
        c_f1 = _metric(candidate.metrics, "f1")
        p_f1 = _metric(champion.metrics, "f1")
        c_brier = _metric(candidate.metrics, "brier")
        p_brier = _metric(champion.metrics, "brier")
        if c_roc is None or p_roc is None:
            return PromotionDecision(
                accepted=False,
                reason="missing roc_auc metric for policy comparison",
                candidate_run_id=run_id,
                champion_before_run_id=champion_run_id,
                checks={},
            )
        checks = {
            "candidate_roc_auc": c_roc,
            "champion_roc_auc": p_roc,
            "roc_auc_delta": c_roc - p_roc,
            "required_roc_auc_delta": settings.auto_promotion_min_roc_auc_delta,
            "candidate_f1": c_f1,
            "champion_f1": p_f1,
            "f1_delta": (c_f1 - p_f1) if c_f1 is not None and p_f1 is not None else None,
            "min_f1_delta": settings.auto_promotion_min_f1_delta,
            "candidate_brier": c_brier,
            "champion_brier": p_brier,
            "brier_increase": (c_brier - p_brier)
            if c_brier is not None and p_brier is not None
            else None,
            "max_brier_increase": settings.auto_promotion_max_brier_increase,
        }
        if (c_roc - p_roc) < settings.auto_promotion_min_roc_auc_delta:
            return PromotionDecision(
                accepted=False,
                reason="roc_auc improvement below threshold",
                candidate_run_id=run_id,
                champion_before_run_id=champion_run_id,
                checks=checks,
            )
        if c_f1 is not None and p_f1 is not None:
            if (c_f1 - p_f1) < settings.auto_promotion_min_f1_delta:
                return PromotionDecision(
                    accepted=False,
                    reason="f1 regression exceeds allowed guardrail",
                    candidate_run_id=run_id,
                    champion_before_run_id=champion_run_id,
                    checks=checks,
                )
        if c_brier is not None and p_brier is not None:
            if (c_brier - p_brier) > settings.auto_promotion_max_brier_increase:
                return PromotionDecision(
                    accepted=False,
                    reason="brier increase exceeds allowed guardrail",
                    candidate_run_id=run_id,
                    champion_before_run_id=champion_run_id,
                    checks=checks,
                )
        return PromotionDecision(
            accepted=True,
            reason="candidate passes promotion policy",
            candidate_run_id=run_id,
            champion_before_run_id=champion_run_id,
            checks=checks,
        )

    async def _persist_promotion_decision(self, run_id: str, decision: PromotionDecision) -> None:
        run = await self.get_status(run_id)
        if run is None:
            return
        metrics = dict(run.metrics or {})
        metrics["promotion_decision"] = {
            "accepted": decision.accepted,
            "reason": decision.reason,
            "candidate_run_id": decision.candidate_run_id,
            "champion_before_run_id": decision.champion_before_run_id,
            "checks": decision.checks or {},
        }
        run.metrics = metrics
        run.updated_at = datetime.now(tz=UTC).isoformat()
        # Keep in-memory registry in sync when run exists there.
        self._registry.update(
            run_id,
            status=run.status,
            dataset_fingerprint=run.dataset_fingerprint,
            artifact_path=run.artifact_path,
            metrics=run.metrics,
            error=run.error,
        )
        await self._experiment_store.upsert(run)


def _metric(metrics: dict[str, Any], name: str) -> float | None:
    raw = metrics.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _prepare_training_frames(
    df: pd.DataFrame,
    feature_set: list[str],
    *,
    train_fraction: float = 0.70,
    val_end_fraction: float = 0.85,
    min_rows: int = 60,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Build supervised frame for one ticker: features at day t, target = 1 iff next day's
    `returns` (close-to-close pct_change on day t+1) is strictly positive.

    `returns` in technical features is `close.pct_change()` — the return **realized on** that
    calendar row; the label uses `returns.shift(-1)` so it never uses the same row's return
    as the thing being predicted (predict direction of *tomorrow's* move).
    """
    if "returns" not in df.columns:
        raise ValueError("combined frame must include 'returns' for target construction")
    if "date" in df.columns:
        work = df.sort_values("date").reset_index(drop=True).copy()
        if work["date"].duplicated().any():
            work = work.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    else:
        work = df.copy()

    missing = [c for c in feature_set if c not in work.columns]
    if missing:
        raise ValueError(f"combined frame missing model features: {','.join(missing[:8])}")

    ret = pd.to_numeric(work["returns"], errors="coerce")
    work["_next_return"] = ret.shift(-1)
    work = work.dropna(subset=["_next_return"])
    work["target"] = (work["_next_return"] > 0.0).astype("int64")
    work = work.drop(columns=["_next_return"])

    work = work.dropna(subset=feature_set)
    if len(work) < min_rows:
        raise ValueError(
            f"need at least {min_rows} rows with valid features and next-day return for train/val/test"
        )

    if not (0.0 < train_fraction < val_end_fraction < 1.0):
        raise ValueError("train_fraction and val_end_fraction must satisfy 0 < train < val_end < 1")

    n = len(work)
    i_val = int(train_fraction * n)
    i_test = int(val_end_fraction * n)
    i_val = max(10, min(i_val, n - 20))
    i_test = max(i_val + 5, min(i_test, n - 5))

    train_df = work.iloc[:i_val].copy()
    val_df = work.iloc[i_val:i_test].copy()
    test_df = work.iloc[i_test:].copy()

    if "date" in train_df.columns and not train_df.empty and not val_df.empty and not test_df.empty:
        tr_end = pd.to_datetime(train_df["date"], errors="coerce").max()
        va_min = pd.to_datetime(val_df["date"], errors="coerce").min()
        va_max = pd.to_datetime(val_df["date"], errors="coerce").max()
        te_min = pd.to_datetime(test_df["date"], errors="coerce").min()
        if pd.isna(tr_end) or pd.isna(va_min) or pd.isna(va_max) or pd.isna(te_min):
            raise ValueError("chronological split: invalid dates")
        if tr_end >= va_min or va_max >= te_min:
            raise ValueError(
                "chronological split invariant failed: train < validation < test on timeline"
            )

    return train_df, val_df, test_df


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
