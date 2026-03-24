import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.contracts.jobs import JobStore
from app.domain.exceptions import (
    FeatureDataMissingError,
    ModelArtifactMissingError,
    UnknownModelError,
)
from app.domain.identifiers import ModelId
from app.jobs.batch_refresh import BatchRefreshOrchestrator
from app.schemas.prediction import (
    EnsureReadyResponse,
    PredictionReadinessResponse,
    PredictionResponse,
    PredictionStatusResponse,
    ReadinessCheck,
    Signal,
)
from app.services.dependencies import (
    get_batch_refresh_orchestrator,
    get_job_store,
    get_prediction_service,
    get_training_service,
)
from app.services.prediction_service import PredictionService
from app.services.training_service import TrainingService

router = APIRouter()


class _ModelSelection(NamedTuple):
    model_id: ModelId
    champion_run_id: str | None
    artifact_path: str | None


async def _resolve_model_selector(model: str, training: TrainingService) -> _ModelSelection:
    raw = model.strip().lower()
    try:
        mid = ModelId(raw)
        return _ModelSelection(model_id=mid, champion_run_id=None, artifact_path=None)
    except ValueError:
        pass

    target: ModelId
    if raw == "champion":
        target = ModelId.MODEL_D
    elif raw.startswith("champion:"):
        suffix = raw.split(":", 1)[1]
        try:
            target = ModelId(suffix)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Unknown model selector: {model!r}") from e
    else:
        raise HTTPException(status_code=422, detail=f"Unknown model selector: {model!r}")

    state = await training.get_lifecycle(target.value)
    if state.champion_run_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"No champion promoted for {target.value}; promote a completed run first",
        )
    champion_run = await training.get_status(state.champion_run_id)
    if champion_run is None or champion_run.artifact_path is None:
        raise HTTPException(
            status_code=422,
            detail=f"Champion artifact is missing for {target.value}; retrain and re-promote",
        )
    return _ModelSelection(
        model_id=target,
        champion_run_id=state.champion_run_id,
        artifact_path=champion_run.artifact_path,
    )


@router.get("/{ticker}", response_model=PredictionResponse)
async def get_prediction(
    ticker: str,
    model: str = Query(
        default="model_d",
        description="Model selector: model_a..model_d or champion[:model_a..model_d].",
    ),
    service: PredictionService = Depends(get_prediction_service),
    training: TrainingService = Depends(get_training_service),
):
    """
    Прогноз вероятности роста акции.
    Возвращает: сигнал (Strong Buy/Buy/Hold/Sell), probability, confidence, объяснение.
    """
    selection = await _resolve_model_selector(model, training)
    try:
        outcome = await service.predict(
            ticker, selection.model_id, artifact_path=selection.artifact_path
        )
    except UnknownModelError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ModelArtifactMissingError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FeatureDataMissingError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    sig: Signal | None = None
    if outcome.signal:
        try:
            sig = Signal(outcome.signal)
        except ValueError:
            sig = None

    return PredictionResponse(
        ticker=outcome.ticker,
        model=outcome.model_id,
        signal=sig,
        probability=outcome.probability,
        confidence=outcome.confidence,
        explanation={
            **(outcome.explanation or {}),
            "resolved_run_id": selection.champion_run_id,
        },
    )


@router.get("/{ticker}/compare")
async def compare_models(ticker: str):
    """Сравнение всех 4 моделей (A, B, C, D) по метрикам и сигналам."""
    return {
        "ticker": ticker.upper(),
        "comparison": {
            "model_a": {},
            "model_b": {},
            "model_c": {},
            "model_d": {},
        },
    }


@router.get("/{ticker}/shap")
async def get_shap_explanation(
    ticker: str,
    model: ModelId = Query(default=ModelId.MODEL_D),
):
    """SHAP values для объяснения предсказания."""
    return {"ticker": ticker.upper(), "model": model.value, "shap_values": {}}


@router.get("/{ticker}/readiness", response_model=PredictionReadinessResponse)
async def get_prediction_readiness(
    ticker: str,
    model: str = Query(
        default="model_d",
        description="Model selector: model_a..model_d or champion[:model_a..model_d].",
    ),
    service: PredictionService = Depends(get_prediction_service),
    training: TrainingService = Depends(get_training_service),
):
    """Readiness checks for prediction dependencies (raw/processed/model artifact)."""
    selection = await _resolve_model_selector(model, training)
    out = await service.readiness(ticker, selection.model_id, artifact_path=selection.artifact_path)
    checks = {
        k: ReadinessCheck(ok=bool(v.get("ok", False)), detail=str(v.get("detail", "")))
        for k, v in out.checks.items()
    }
    return PredictionReadinessResponse(
        ticker=out.ticker,
        model=out.model_id,
        ready=out.ready,
        checks=checks,
    )


class EnsureReadyBody(BaseModel):
    force_full: bool = False
    refresh_quote: bool = True
    refresh_fundamentals: bool = True
    run_etl: bool = True


def _freshness_payload(path_str: str) -> dict[str, object]:
    path = Path(path_str)
    if not path.exists():
        return {"exists": False, "path": path_str, "age_sec": None}
    age_sec = max(0.0, time.time() - path.stat().st_mtime)
    return {"exists": True, "path": path_str, "age_sec": round(age_sec, 3)}


def _recommended_action(
    *,
    ready: bool,
    checks: dict[str, dict[str, object]],
) -> str:
    if ready:
        return "ready_for_predict"
    if not bool(checks.get("model_artifact", {}).get("ok", False)):
        return "train_or_load_model_artifact"
    if not bool(checks.get("processed_technical", {}).get("ok", False)):
        return "run_ensure_ready_with_etl"
    if not bool(checks.get("raw_ohlcv", {}).get("ok", False)):
        return "run_ensure_ready_refresh_raw"
    return "inspect_checks_and_run_ensure_ready"


@router.post(
    "/{ticker}/ensure-ready",
    response_model=EnsureReadyResponse,
    responses={
        422: {"description": "Unknown model id or invalid input"},
        503: {"description": "Upstream/service dependency unavailable"},
    },
)
async def ensure_prediction_ready(
    ticker: str,
    body: EnsureReadyBody,
    model: str = Query(
        default="model_d",
        description="Model selector: model_a..model_d or champion[:model_a..model_d].",
    ),
    service: PredictionService = Depends(get_prediction_service),
    orchestrator: BatchRefreshOrchestrator = Depends(get_batch_refresh_orchestrator),
    training: TrainingService = Depends(get_training_service),
):
    """
    Try to make ticker prediction-ready:
    1) read readiness snapshot
    2) run one-ticker refresh workflow (optionally ETL)
    3) read readiness again and return before/after delta
    """
    selection = await _resolve_model_selector(model, training)
    before = await service.readiness(
        ticker, selection.model_id, artifact_path=selection.artifact_path
    )
    run_id = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    status_path, lineage_path = await orchestrator.run(
        tickers=[ticker.strip().upper()],
        run_id=run_id,
        force_full=body.force_full,
        refresh_quote=body.refresh_quote,
        refresh_fundamentals=body.refresh_fundamentals,
        run_etl=body.run_etl,
    )
    after = await service.readiness(
        ticker, selection.model_id, artifact_path=selection.artifact_path
    )
    checks_before = {
        k: ReadinessCheck(ok=bool(v.get("ok", False)), detail=str(v.get("detail", "")))
        for k, v in before.checks.items()
    }
    checks_after = {
        k: ReadinessCheck(ok=bool(v.get("ok", False)), detail=str(v.get("detail", "")))
        for k, v in after.checks.items()
    }
    return EnsureReadyResponse(
        ticker=after.ticker,
        model=after.model_id,
        before_ready=before.ready,
        after_ready=after.ready,
        changed=before.ready != after.ready,
        run_id=run_id,
        status_path=str(status_path),
        lineage_path=str(lineage_path),
        checks_before=checks_before,
        checks_after=checks_after,
    )


@router.get(
    "/{ticker}/status",
    response_model=PredictionStatusResponse,
    responses={422: {"description": "Unknown model id or invalid input"}},
)
async def get_prediction_status(
    ticker: str,
    model: str = Query(
        default="model_d",
        description="Model selector: model_a..model_d or champion[:model_a..model_d].",
    ),
    service: PredictionService = Depends(get_prediction_service),
    store: JobStore = Depends(get_job_store),
    training: TrainingService = Depends(get_training_service),
):
    """
    Operational status for one ticker in one response:
    readiness + freshness + latest job row + recommended action.
    """
    selection = await _resolve_model_selector(model, training)
    out = await service.readiness(ticker, selection.model_id, artifact_path=selection.artifact_path)
    checks = out.checks
    freshness: dict[str, dict[str, object]] = {}
    for key in (
        "raw_ohlcv",
        "raw_fundamentals",
        "processed_technical",
        "processed_fundamental",
        "model_artifact",
    ):
        detail = str(checks.get(key, {}).get("detail", ""))
        freshness[key] = _freshness_payload(detail)

    checks_model = {
        k: ReadinessCheck(ok=bool(v.get("ok", False)), detail=str(v.get("detail", "")))
        for k, v in checks.items()
    }
    latest_job = await asyncio.to_thread(store.latest_lineage_for_ticker, out.ticker)
    return PredictionStatusResponse(
        ticker=out.ticker,
        model=out.model_id,
        ready=out.ready,
        recommended_action=_recommended_action(ready=out.ready, checks=checks),
        checks=checks_model,
        freshness=freshness,
        latest_job=latest_job,
    )
