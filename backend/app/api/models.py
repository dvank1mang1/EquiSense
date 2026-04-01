from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from app.domain.identifiers import ModelId
from app.services.dependencies import get_training_service
from app.services.training_service import TrainingService

router = APIRouter()


@router.get("/")
async def list_models():
    """Список доступных ML-моделей и их описания."""
    return {
        "models": [
            {
                "id": "baseline_lr",
                "name": "Logistic Regression (baseline)",
                "features": ["technical"],
                "algorithm": "LogisticRegression",
                "description": "Linear baseline — same technical features as Model A. "
                "Use to quantify the non-linear gain of tree-based ensembles.",
            },
            {
                "id": "model_a",
                "name": "Technical Only",
                "features": ["technical"],
                "algorithm": "XGBoost",
            },
            {
                "id": "model_b",
                "name": "Technical + Fundamental",
                "features": ["technical", "fundamental"],
                "algorithm": "LightGBM",
            },
            {
                "id": "model_c",
                "name": "Technical + News",
                "features": ["technical", "news"],
                "algorithm": "RandomForest",
            },
            {
                "id": "model_d",
                "name": "All Features",
                "features": ["technical", "fundamental", "news"],
                "algorithm": "XGBoost",
            },
            {
                "id": "model_e",
                "name": "All Features (HistGradientBoosting)",
                "features": ["technical", "fundamental", "news"],
                "algorithm": "HistGradientBoostingClassifier",
                "description": "Sklearn HGBM on the full tabular feature set; strong default for noisy structured data.",
            },
            {
                "id": "model_f",
                "name": "All Features (Voting ensemble)",
                "features": ["technical", "fundamental", "news"],
                "algorithm": "VotingClassifier(XGBoost, LightGBM)",
                "description": "Soft-voting blend of gradient boosting variants with different inductive bias.",
            },
        ]
    }


@router.get("/{model_id}/metrics")
async def get_model_metrics(model_id: str):
    """ML-метрики модели: F1, ROC-AUC, Precision, Recall."""
    return {
        "model_id": model_id,
        "metrics": {
            "f1": None,
            "roc_auc": None,
            "precision": None,
            "recall": None,
        },
    }


class TrainModelBody(BaseModel):
    ticker: str


class TrainModelResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    model_id: str
    ticker: str
    status: str


class TrainingRunStatusResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

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


class ExperimentListResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    items: list[TrainingRunStatusResponse]
    total: int = Field(..., ge=0)


class PromoteChampionBody(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    reason: str = Field(default="manual promotion", min_length=3, max_length=200)
    force: bool = False


class ModelLifecycleResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    champion_run_id: str | None = None
    updated_at: str
    history: list[dict[str, str]]
    promotion_decision: dict[str, Any] | None = None


class ChampionCatalogEntry(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    champion_run_id: str | None = None
    updated_at: str


class ChampionCatalogResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    items: list[ChampionCatalogEntry]
    total: int = Field(..., ge=0)


@router.post("/{model_id}/train")
async def train_model(
    model_id: str,
    body: TrainModelBody,
    service: TrainingService = Depends(get_training_service),
):
    """Запустить обучение модели (фоновая задача) и вернуть run_id."""
    logger.info("models.train start model_id={} ticker={}", model_id, body.ticker.strip().upper())
    try:
        mid = ModelId(model_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Unknown model id: {model_id!r}") from e
    run = await service.start_training(mid, body.ticker)
    resp = TrainModelResponse(
        run_id=run.run_id,
        model_id=run.model_id,
        ticker=run.ticker,
        status=run.status,
    )
    logger.info(
        "models.train queued model_id={} ticker={} run_id={}",
        resp.model_id,
        resp.ticker,
        resp.run_id,
    )
    return resp


@router.get("/{model_id}/train/{run_id}")
async def get_train_status(
    model_id: str,
    run_id: str,
    service: TrainingService = Depends(get_training_service),
):
    _ = model_id
    logger.info("models.train_status get model_id={} run_id={}", model_id, run_id)
    run = await service.get_status(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown training run id: {run_id}")
    return TrainingRunStatusResponse(
        run_id=run.run_id,
        model_id=run.model_id,
        ticker=run.ticker,
        status=run.status,
        created_at=run.created_at,
        updated_at=run.updated_at,
        params=run.params,
        dataset_fingerprint=run.dataset_fingerprint,
        artifact_path=run.artifact_path,
        metrics=run.metrics,
        error=run.error,
    )


@router.get("/{model_id}/lifecycle", response_model=ModelLifecycleResponse)
async def get_model_lifecycle(
    model_id: str,
    service: TrainingService = Depends(get_training_service),
):
    try:
        _ = ModelId(model_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Unknown model id: {model_id!r}") from e
    state = await service.get_lifecycle(model_id)
    return ModelLifecycleResponse(
        model_id=state.model_id,
        champion_run_id=state.champion_run_id,
        updated_at=state.updated_at,
        history=state.history,
    )


@router.get("/lifecycle/champions", response_model=ChampionCatalogResponse)
async def list_champions(
    service: TrainingService = Depends(get_training_service),
):
    states = await service.list_lifecycles()
    items = [
        ChampionCatalogEntry(
            model_id=s.model_id,
            champion_run_id=s.champion_run_id,
            updated_at=s.updated_at,
        )
        for s in states
    ]
    return ChampionCatalogResponse(items=items, total=len(items))


@router.post("/{model_id}/lifecycle/promote/{run_id}", response_model=ModelLifecycleResponse)
async def promote_model_champion(
    model_id: str,
    run_id: str,
    body: PromoteChampionBody,
    service: TrainingService = Depends(get_training_service),
):
    logger.info(
        "models.promote start model_id={} run_id={} reason={}",
        model_id,
        run_id,
        body.reason,
    )
    try:
        _ = ModelId(model_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Unknown model id: {model_id!r}") from e
    try:
        state, decision = await service.promote_champion(
            model_id, run_id, reason=body.reason, force=body.force
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    resp = ModelLifecycleResponse(
        model_id=state.model_id,
        champion_run_id=state.champion_run_id,
        updated_at=state.updated_at,
        history=state.history,
        promotion_decision={
            "accepted": decision.accepted,
            "reason": decision.reason,
            "candidate_run_id": decision.candidate_run_id,
            "champion_before_run_id": decision.champion_before_run_id,
            "checks": decision.checks or {},
        },
    )
    logger.info(
        "models.promote done model_id={} champion_run_id={}",
        resp.model_id,
        resp.champion_run_id,
    )
    return resp


class NightlyModelSummary(BaseModel):
    model_id: str
    latest_run_id: str | None = None
    latest_status: str | None = None
    latest_metrics: dict[str, Any] | None = None
    champion_run_id: str | None = None
    promotion_decision: dict[str, Any] | None = None


class NightlySummaryResponse(BaseModel):
    items: list[NightlyModelSummary]
    total: int = Field(..., ge=0)


@router.get("/nightly/summary", response_model=NightlySummaryResponse)
async def get_nightly_summary(
    limit_per_model: int = Query(default=1, ge=1, le=5),
    service: TrainingService = Depends(get_training_service),
):
    from app.domain.identifiers import ROLLOUT_MODEL_IDS

    items: list[NightlyModelSummary] = []
    for mid in ROLLOUT_MODEL_IDS:
        runs = await service.list_experiments(
            model_id=mid.value, ticker=None, limit=limit_per_model
        )
        latest = runs[0] if runs else None
        lifecycle = await service.get_lifecycle(mid.value)
        promotion_decision = None
        if latest and latest.metrics and isinstance(latest.metrics.get("promotion_decision"), dict):
            promotion_decision = latest.metrics.get("promotion_decision")
        items.append(
            NightlyModelSummary(
                model_id=mid.value,
                latest_run_id=latest.run_id if latest else None,
                latest_status=latest.status if latest else None,
                latest_metrics=latest.metrics if latest else None,
                champion_run_id=lifecycle.champion_run_id,
                promotion_decision=promotion_decision,
            )
        )
    return NightlySummaryResponse(items=items, total=len(items))


@router.get("/{model_id}/experiments", response_model=ExperimentListResponse)
async def list_model_experiments(
    model_id: str,
    ticker: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    service: TrainingService = Depends(get_training_service),
):
    try:
        _ = ModelId(model_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Unknown model id: {model_id!r}") from e
    runs = await service.list_experiments(model_id=model_id, ticker=ticker, limit=limit)
    items = [
        TrainingRunStatusResponse(
            run_id=run.run_id,
            model_id=run.model_id,
            ticker=run.ticker,
            status=run.status,
            created_at=run.created_at,
            updated_at=run.updated_at,
            params=run.params,
            dataset_fingerprint=run.dataset_fingerprint,
            artifact_path=run.artifact_path,
            metrics=run.metrics,
            error=run.error,
        )
        for run in runs
    ]
    return ExperimentListResponse(items=items, total=len(items))


@router.get("/{model_id}/experiments/{run_id}", response_model=TrainingRunStatusResponse)
async def get_model_experiment(
    model_id: str,
    run_id: str,
    service: TrainingService = Depends(get_training_service),
):
    try:
        _ = ModelId(model_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Unknown model id: {model_id!r}") from e
    run = await service.get_status(run_id)
    if run is None or run.model_id != model_id:
        raise HTTPException(status_code=404, detail=f"Unknown experiment id: {run_id}")
    return TrainingRunStatusResponse(
        run_id=run.run_id,
        model_id=run.model_id,
        ticker=run.ticker,
        status=run.status,
        created_at=run.created_at,
        updated_at=run.updated_at,
        params=run.params,
        dataset_fingerprint=run.dataset_fingerprint,
        artifact_path=run.artifact_path,
        metrics=run.metrics,
        error=run.error,
    )
