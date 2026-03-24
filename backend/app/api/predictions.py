from fastapi import APIRouter, Depends, HTTPException, Query

from app.domain.exceptions import (
    FeatureDataMissingError,
    ModelArtifactMissingError,
    UnknownModelError,
)
from app.domain.identifiers import ModelId
from app.schemas.prediction import PredictionResponse, Signal
from app.services.dependencies import get_prediction_service
from app.services.prediction_service import PredictionService

router = APIRouter()


@router.get("/{ticker}", response_model=PredictionResponse)
async def get_prediction(
    ticker: str,
    model: ModelId = Query(
        default=ModelId.MODEL_D,
        description="Registered model id (model_a … model_d).",
    ),
    service: PredictionService = Depends(get_prediction_service),
):
    """
    Прогноз вероятности роста акции.
    Возвращает: сигнал (Strong Buy/Buy/Hold/Sell), probability, confidence, объяснение.
    """
    try:
        outcome = await service.predict(ticker, model)
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
        explanation=outcome.explanation,
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
