from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()


@router.get("/{ticker}")
async def get_prediction(
    ticker: str,
    model: Optional[str] = Query("model_d", description="model_a | model_b | model_c | model_d"),
):
    """
    Прогноз вероятности роста акции.
    Возвращает: сигнал (Strong Buy/Buy/Hold/Sell), probability, confidence, объяснение.
    """
    return {
        "ticker": ticker.upper(),
        "model": model,
        "signal": None,
        "probability": None,
        "confidence": None,
        "explanation": {},
    }


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
    model: Optional[str] = Query("model_d"),
):
    """SHAP values для объяснения предсказания."""
    return {"ticker": ticker.upper(), "model": model, "shap_values": {}}
