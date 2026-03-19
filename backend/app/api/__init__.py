from fastapi import APIRouter
from app.api import stocks, predictions, backtesting, models

router = APIRouter()

router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
router.include_router(backtesting.router, prefix="/backtesting", tags=["backtesting"])
router.include_router(models.router, prefix="/models", tags=["models"])
