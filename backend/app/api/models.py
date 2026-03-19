from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_models():
    """Список доступных ML-моделей и их описания."""
    return {
        "models": [
            {"id": "model_a", "name": "Technical Only", "features": ["technical"]},
            {"id": "model_b", "name": "Technical + Fundamental", "features": ["technical", "fundamental"]},
            {"id": "model_c", "name": "Technical + News", "features": ["technical", "news"]},
            {"id": "model_d", "name": "All Features", "features": ["technical", "fundamental", "news"]},
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


@router.post("/{model_id}/train")
async def train_model(model_id: str):
    """Запустить обучение модели (фоновая задача)."""
    return {"model_id": model_id, "status": "training_started"}
