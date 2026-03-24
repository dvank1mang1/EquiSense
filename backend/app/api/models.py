from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.domain.identifiers import ModelId
from app.services.dependencies import get_training_service
from app.services.training_service import TrainingService

router = APIRouter()


@router.get("/")
async def list_models():
    """Список доступных ML-моделей и их описания."""
    return {
        "models": [
            {"id": "model_a", "name": "Technical Only", "features": ["technical"]},
            {
                "id": "model_b",
                "name": "Technical + Fundamental",
                "features": ["technical", "fundamental"],
            },
            {"id": "model_c", "name": "Technical + News", "features": ["technical", "news"]},
            {
                "id": "model_d",
                "name": "All Features",
                "features": ["technical", "fundamental", "news"],
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


@router.post("/{model_id}/train")
async def train_model(
    model_id: str,
    body: TrainModelBody,
    service: TrainingService = Depends(get_training_service),
):
    """Запустить обучение модели (фоновая задача) и вернуть run_id."""
    try:
        mid = ModelId(model_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Unknown model id: {model_id!r}") from e
    run = await service.start_training(mid, body.ticker)
    return TrainModelResponse(
        run_id=run.run_id,
        model_id=run.model_id,
        ticker=run.ticker,
        status=run.status,
    )


@router.get("/{model_id}/train/{run_id}")
async def get_train_status(
    model_id: str,
    run_id: str,
    service: TrainingService = Depends(get_training_service),
):
    _ = model_id
    run = service.get_status(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown training run id: {run_id}")
    return {
        "run_id": run.run_id,
        "model_id": run.model_id,
        "ticker": run.ticker,
        "status": run.status,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "error": run.error,
    }
