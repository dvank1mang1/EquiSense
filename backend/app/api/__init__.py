from fastapi import APIRouter

from app.api import backtesting, jobs, meta, models, predictions, stocks

router = APIRouter()

router.include_router(meta.router, prefix="", tags=["meta"])
router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
router.include_router(backtesting.router, prefix="/backtesting", tags=["backtesting"])
router.include_router(models.router, prefix="/models", tags=["models"])
router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
