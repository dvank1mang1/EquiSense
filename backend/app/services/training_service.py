from __future__ import annotations

import asyncio
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from app.contracts.features import FeatureStorePort
from app.core.config import get_settings
from app.domain.identifiers import ModelId
from app.ml.evaluation import (
    financial_selection_metrics,
    information_coefficient_metrics,
    precision_recall_at_k,
    reliability_curve_and_ece,
)
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


OfflineMetricsSource = Literal[
    "same_ticker_holdout",
    "none",
    "other_ticker_champion",
    "other_ticker_flat_file",
]


@dataclass(frozen=True)
class OfflineMetricsResult:
    """Holdout metrics for UI; ``trained_ticker`` is the symbol the numbers actually describe."""

    metrics: dict[str, float | None]
    source: OfflineMetricsSource
    trained_ticker: str | None = None


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

    async def resolve_inference_artifact(self, model_id: ModelId) -> tuple[str | None, str | None]:
        """
        Resolve which file to load for inference.

        Order: canonical ``{model_dir}/{model_id}.joblib`` (use default path in service)
        → promoted champion run → latest completed experiment with an on-disk artifact.

        Returns ``(artifact_path, run_id)``. ``(None, None)`` means the flat canonical
        file exists and callers should pass ``artifact_path=None`` to :meth:`load`.
        """
        settings = get_settings()
        flat = Path(settings.model_dir) / f"{model_id.value}.joblib"
        if flat.is_file():
            return None, None

        state = await self.get_lifecycle(model_id.value)
        if state.champion_run_id:
            run = await self.get_status(state.champion_run_id)
            if run and run.artifact_path:
                p = Path(run.artifact_path)
                if p.is_file():
                    return str(p), state.champion_run_id

        for run in await self.list_experiments(model_id=model_id.value, limit=50):
            if run.status != "completed" or not run.artifact_path:
                continue
            p = Path(run.artifact_path)
            if p.is_file():
                return str(p), run.run_id

        # After API restart in-memory registry is empty; artifacts may still exist on disk.
        model_root = Path(settings.model_dir) / model_id.value
        if model_root.is_dir():
            found = sorted(
                model_root.glob("*/model.joblib"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if found:
                best = found[0]
                return str(best), best.parent.name

        return None, None

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

                is_ranker = bool(getattr(instance, "is_ranking_model", False))
                if is_ranker:
                    imputer = SimpleImputer(strategy="median")
                    x_train_i = pd.DataFrame(
                        imputer.fit_transform(x_train),
                        columns=instance.feature_set,
                        index=x_train.index,
                    )
                    train_dates = pd.to_datetime(train_df["date"], errors="coerce").dt.normalize()
                    group = [
                        int(v) for v in train_dates.value_counts(sort=False).sort_index().values
                    ]
                    await asyncio.to_thread(
                        instance.fit_ranker,  # type: ignore[attr-defined]
                        x_train_i,
                        y_train,
                        group=group,
                    )
                    # Persist preprocessing in-model for compatible inference path.
                    instance.model = Pipeline([("imputer", imputer), ("ranker", instance.model)])
                    calibration_status = "skipped_ranking_model"
                else:
                    await asyncio.to_thread(fit_production_pipeline, instance, x_train, y_train)
                    calibration_status = await asyncio.to_thread(
                        calibrate_production_model,
                        instance,
                        x_val,
                        y_val,
                        min_samples=settings.training_calibration_min_val_samples,
                    )
                metrics = await asyncio.to_thread(instance.evaluate, x_test, y_test)
                proba = await asyncio.to_thread(instance.predict_proba, x_test)
                y_score = pd.Series(proba[:, 1], index=test_df.index, dtype=float)
                rank_k = max(1, int(len(test_df) * 0.25))
                ranking_metrics = precision_recall_at_k(y_test, y_score, k=rank_k)
                eval_frame = pd.DataFrame(
                    {
                        "date": test_df.get("date"),
                        "score": y_score,
                        "forward_return": pd.to_numeric(test_df["forward_return"], errors="coerce"),
                    }
                )
                fin_metrics = financial_selection_metrics(eval_frame)
                ic_metrics = information_coefficient_metrics(eval_frame, include_negated_score=True)
                reliability_df, ece = reliability_curve_and_ece(y_test, y_score, n_bins=10)
                prev = float(pd.to_numeric(y_test, errors="coerce").astype(float).mean())
                pr_auc_val = float(metrics.get("pr_auc", float("nan")))
                pr_minus_prev = (
                    float(pr_auc_val - prev)
                    if pr_auc_val == pr_auc_val and prev == prev
                    else float("nan")
                )
                artifact_path = str(_artifact_path_for_run(model_id.value, run.run_id))
                await asyncio.to_thread(instance.save, artifact_path)
                # metrics dict built below; disk copy uses the same numbers as experiment store
                metrics = {
                    "ticker": sym,
                    "accuracy": float(metrics.get("accuracy", float("nan"))),
                    "f1": float(metrics["f1"]),
                    "roc_auc": float(metrics["roc_auc"]),
                    "pr_auc": float(metrics["pr_auc"]),
                    "pr_auc_minus_prevalence": pr_minus_prev,
                    "brier": float(metrics["brier"]),
                    "precision": float(metrics["precision"]),
                    "recall": float(metrics["recall"]),
                    "test_prevalence_positive": prev,
                    "train_rows": int(len(train_df)),
                    "val_rows": int(len(val_df)),
                    "test_rows": int(len(test_df)),
                    "calibration": calibration_status,
                    "calibration_isotonic": calibration_status == "isotonic_applied",
                    "precision_at_k": float(ranking_metrics["precision_at_k"]),
                    "recall_at_k": float(ranking_metrics["recall_at_k"]),
                    "rank_k": int(rank_k),
                    "ece": float(ece),
                    "reliability_curve": reliability_df.to_dict(orient="records"),
                    **{k: float(v) for k, v in fin_metrics.items()},
                    **{k: float(v) for k, v in ic_metrics.items()},
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
                try:
                    await asyncio.to_thread(
                        _persist_metrics_alongside_artifact, artifact_path, sym, metrics
                    )
                except Exception as werr:  # noqa: BLE001
                    logger.warning(
                        "Could not write metrics.json beside {}: {}", artifact_path, werr
                    )

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

    async def offline_metrics_for_ticker_model(
        self, model_id: ModelId, ticker: str
    ) -> OfflineMetricsResult:
        """
        Holdout metrics for UI.

        Prefer the latest completed training **on the requested ticker**. If none, fall back to
        the promoted champion run or ``{model_id}.metrics.json`` so flat joblib demos still show
        numbers (clearly labeled as another ticker in ``trained_ticker`` / ``source``).
        """
        sym = ticker.strip().upper()
        metric_keys = (
            "accuracy",
            "f1",
            "roc_auc",
            "pr_auc",
            "pr_auc_minus_prevalence",
            "brier",
            "precision",
            "recall",
            "ece",
            "precision_at_k",
            "recall_at_k",
            "ic_mean",
            "rank_ic_mean",
            "ic_mean_neg_score",
            "rank_ic_mean_neg_score",
            "test_prevalence_positive",
            "long_short_spread",
        )
        empty: dict[str, float | None] = {k: None for k in metric_keys}
        seen: set[str] = set()
        ordered: list[TrainingRun] = []

        def add(run: TrainingRun | None) -> None:
            if run is None or run.run_id in seen:
                return
            seen.add(run.run_id)
            ordered.append(run)

        _, run_id = await self.resolve_inference_artifact(model_id)
        if run_id:
            r = await self.get_status(run_id)
            if r is not None and r.ticker == sym:
                add(r)
        for r in await self.list_experiments(model_id=model_id.value, ticker=sym, limit=40):
            add(r)

        for run in ordered:
            if run.status != "completed" or not run.metrics:
                continue
            got = _fill_metric_columns(run.metrics, metric_keys)
            if got is not None:
                return OfflineMetricsResult(got, "same_ticker_holdout", sym)

        model_dir = Path(get_settings().model_dir).resolve()
        sidecar = model_dir / f"{model_id.value}.metrics.json"
        if sidecar.is_file():
            try:
                raw = json.loads(sidecar.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, TypeError):
                raw = {}
            if isinstance(raw, dict) and str(raw.get("ticker", "")).strip().upper() == sym:
                got = _fill_metric_columns(raw, metric_keys)
                if got is not None:
                    return OfflineMetricsResult(got, "same_ticker_holdout", sym)

        nested = _load_nested_run_metrics_json(model_dir, model_id.value, sym)
        if nested is not None:
            got = _fill_metric_columns(nested, metric_keys)
            if got is not None:
                return OfflineMetricsResult(got, "same_ticker_holdout", sym)

        apath, _ = await self.resolve_inference_artifact(model_id)
        if apath:
            beside = Path(apath).parent / "metrics.json"
            if beside.is_file():
                try:
                    raw2 = json.loads(beside.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, TypeError):
                    raw2 = {}
                if isinstance(raw2, dict) and str(raw2.get("ticker", "")).strip().upper() == sym:
                    got = _fill_metric_columns(raw2, metric_keys)
                    if got is not None:
                        return OfflineMetricsResult(got, "same_ticker_holdout", sym)

        # --- Fallbacks: last known training for this model slot (may be a different ticker) ---
        state = await self.get_lifecycle(model_id.value)
        if state.champion_run_id:
            champ = await self.get_status(state.champion_run_id)
            if (
                champ is not None
                and champ.model_id == model_id.value
                and champ.status == "completed"
                and champ.metrics
            ):
                got = _fill_metric_columns(champ.metrics, metric_keys)
                if got is not None:
                    ct = champ.ticker.strip().upper()
                    src: OfflineMetricsSource = (
                        "same_ticker_holdout" if ct == sym else "other_ticker_champion"
                    )
                    return OfflineMetricsResult(
                        got, src, ct if src == "other_ticker_champion" else sym
                    )

        if sidecar.is_file():
            try:
                raw3 = json.loads(sidecar.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, TypeError):
                raw3 = {}
            if isinstance(raw3, dict):
                got = _fill_metric_columns(raw3, metric_keys)
                if got is not None:
                    ft = str(raw3.get("ticker", "") or "").strip().upper() or None
                    if ft == sym:
                        return OfflineMetricsResult(got, "same_ticker_holdout", sym)
                    return OfflineMetricsResult(
                        got,
                        "other_ticker_flat_file",
                        ft,
                    )

        return OfflineMetricsResult(dict(empty), "none", None)

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


def _json_normalize_for_disk(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {str(k): _json_normalize_for_disk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_normalize_for_disk(v) for v in obj]
    return obj


def _persist_metrics_alongside_artifact(
    artifact_path: str, sym: str, metrics: dict[str, Any]
) -> None:
    """So /compare can load holdout metrics when Postgres is down (flat joblib or after restart)."""
    path = Path(artifact_path).parent / "metrics.json"
    payload = _json_normalize_for_disk(dict(metrics))
    if not isinstance(payload, dict):
        return
    payload["ticker"] = sym
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _load_nested_run_metrics_json(
    model_dir: Path, model_id_str: str, sym: str
) -> dict[str, Any] | None:
    """``{model_dir}/{model_id}/{run_id}/metrics.json`` written after training."""
    root = model_dir / model_id_str
    if not root.is_dir():
        return None
    candidates: list[tuple[float, Path]] = []
    for p in root.glob("*/metrics.json"):
        try:
            candidates.append((p.stat().st_mtime, p))
        except OSError:
            continue
    for _, p in sorted(candidates, key=lambda t: t[0], reverse=True):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
        if isinstance(raw, dict) and str(raw.get("ticker", "")).strip().upper() == sym:
            return raw
    return None


def _metric(metrics: dict[str, Any], name: str) -> float | None:
    raw = metrics.get(name)
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    if abs(v) == float("inf"):
        return None
    return v


def _metrics_blob_usable(m: dict[str, Any]) -> bool:
    """True if dict looks like a classification holdout blob (not only IC/spread keys)."""
    if _metric(m, "f1") is not None or _metric(m, "roc_auc") is not None:
        return True
    if _metric(m, "pr_auc") is not None:
        return True
    if _metric(m, "accuracy") is not None:
        return True
    return False


def _fill_metric_columns(
    m: dict[str, Any], metric_keys: tuple[str, ...]
) -> dict[str, float | None] | None:
    if not _metrics_blob_usable(m):
        return None
    return {k: _metric(m, k) for k in metric_keys}


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
    work["forward_return"] = ret.shift(-1)
    work = work.dropna(subset=["forward_return"])
    work["target"] = (work["forward_return"] > 0.0).astype("int64")

    # Sparse fundamental/sentiment columns would drop almost all rows with dropna(subset=feature_set).
    # Median imputation runs on train; keep rows that have at least one non-null model feature.
    feat_block = work.reindex(columns=list(feature_set))
    work = work.loc[~feat_block.isna().all(axis=1)].copy()
    if len(work) < min_rows:
        raise ValueError(
            f"need at least {min_rows} rows with valid features and next-day return for train/val/test"
        )

    if not (0.0 < train_fraction < val_end_fraction < 1.0):
        raise ValueError("train_fraction and val_end_fraction must satisfy 0 < train < val_end < 1")

    if "date" not in work.columns:
        n = len(work)
        i_val = int(train_fraction * n)
        i_test = int(val_end_fraction * n)
        i_val = max(10, min(i_val, n - 20))
        i_test = max(i_val + 5, min(i_test, n - 5))
        train_df = work.iloc[:i_val].copy()
        val_df = work.iloc[i_val:i_test].copy()
        test_df = work.iloc[i_test:].copy()
    else:
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
        work = work.dropna(subset=["date"]).copy()
        unique_dates = np.sort(work["date"].dt.normalize().unique())
        if len(unique_dates) < 20:
            raise ValueError("not enough unique dates for train/validation/test split")
        i_val = max(5, min(int(train_fraction * len(unique_dates)), len(unique_dates) - 10))
        i_test = max(
            i_val + 3,
            min(int(val_end_fraction * len(unique_dates)), len(unique_dates) - 3),
        )
        train_dates = set(unique_dates[:i_val])
        val_dates = set(unique_dates[i_val:i_test])
        test_dates = set(unique_dates[i_test:])
        train_df = work[work["date"].dt.normalize().isin(train_dates)].copy()
        val_df = work[work["date"].dt.normalize().isin(val_dates)].copy()
        test_df = work[work["date"].dt.normalize().isin(test_dates)].copy()

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
