"""Lightweight discovery for `/api/v1` (product / integrations)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/", summary="API v1 index")
async def api_v1_root() -> dict[str, object]:
    return {
        "api_version": "v1",
        "release": settings.app_version,
        "docs": {"swagger": "/docs", "redoc": "/redoc"},
        "health": "/health",
        "routers": {
            "stocks": "/api/v1/stocks",
            "predictions": "/api/v1/predictions",
            "backtesting": "/api/v1/backtesting",
            "models": "/api/v1/models",
            "jobs": "/api/v1/jobs",
        },
    }
