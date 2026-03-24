from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.jobs.batch_refresh import (
    BatchRefreshOrchestrator,
    lineage_path_for_run,
    metrics_path_for_run,
    status_path_for_run,
)
from app.jobs.registry import InMemoryJobRegistry, get_job_registry
from app.services.dependencies import get_batch_refresh_orchestrator

router = APIRouter()


class RefreshUniverseBody(BaseModel):
    tickers: list[str] = Field(default_factory=list, min_length=1)
    force_full: bool = False
    refresh_quote: bool = True
    refresh_fundamentals: bool = True
    retry_attempts: int = Field(3, ge=1, le=10)
    retry_wait_sec: float = Field(2.0, ge=0.0, le=120.0)
    background: bool = True


def _new_run_id() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


async def _run_job(
    orchestrator: BatchRefreshOrchestrator,
    body: RefreshUniverseBody,
    run_id: str,
) -> tuple[str, str]:
    status_path, lineage_path = await orchestrator.run(
        tickers=[t.strip().upper() for t in body.tickers],
        run_id=run_id,
        force_full=body.force_full,
        refresh_quote=body.refresh_quote,
        refresh_fundamentals=body.refresh_fundamentals,
    )
    return str(status_path), str(lineage_path)


@router.post("/refresh-universe")
async def refresh_universe(
    body: RefreshUniverseBody,
    base_orchestrator: BatchRefreshOrchestrator = Depends(get_batch_refresh_orchestrator),
    registry: InMemoryJobRegistry = Depends(get_job_registry),
):
    orchestrator = BatchRefreshOrchestrator(
        market=base_orchestrator._market,  # controlled adaptation for per-run retry settings
        fundamentals=base_orchestrator._fundamentals,
        retry_attempts=body.retry_attempts,
        retry_wait_sec=body.retry_wait_sec,
    )
    run_id = _new_run_id()

    if body.background:
        task = asyncio.create_task(_run_job(orchestrator, body, run_id))
        registry.register(run_id, task)
        return {
            "run_id": run_id,
            "status": "running",
            "status_path": str(status_path_for_run(run_id)),
            "lineage_path": str(lineage_path_for_run(run_id)),
            "metrics_path": str(metrics_path_for_run(run_id)),
        }

    status_path, lineage_path = await _run_job(orchestrator, body, run_id)
    return {
        "run_id": run_id,
        "status": "completed",
        "status_path": status_path,
        "lineage_path": lineage_path,
        "metrics_path": str(metrics_path_for_run(run_id)),
    }


@router.get("/refresh-universe/{run_id}")
async def get_refresh_universe_status(
    run_id: str,
    registry: InMemoryJobRegistry = Depends(get_job_registry),
):
    path = status_path_for_run(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run id not found")

    payload = json.loads(path.read_text(encoding="utf-8"))
    handle = registry.get(run_id)
    payload["runtime_status"] = handle.status if handle is not None else "completed"
    return payload


@router.get("/refresh-universe/{run_id}/metrics")
async def get_refresh_universe_metrics(run_id: str):
    path = metrics_path_for_run(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Metrics for run id not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/refresh-universe/{run_id}/lineage")
async def get_refresh_universe_lineage(
    run_id: str,
    limit: int = Query(100, ge=1, le=10000),
):
    path = lineage_path_for_run(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Lineage for run id not found")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[:limit]:
        if line.strip():
            rows.append(json.loads(line))
    return {
        "run_id": run_id,
        "lineage_path": str(path),
        "rows": rows,
    }
