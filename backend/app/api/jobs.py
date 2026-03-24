from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.contracts.jobs import JobStore
from app.core.config import settings
from app.jobs.batch_refresh import (
    BatchRefreshOrchestrator,
)
from app.jobs.queue import get_job_queue, safe_queue_status
from app.jobs.registry import InMemoryJobRegistry, get_job_registry
from app.services.dependencies import get_batch_refresh_orchestrator, get_job_store

router = APIRouter()


class RefreshUniverseBody(BaseModel):
    tickers: list[str] = Field(default_factory=list, min_length=1)
    force_full: bool = False
    refresh_quote: bool = True
    refresh_fundamentals: bool = True
    run_etl: bool = False
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
        run_etl=body.run_etl,
    )
    return str(status_path), str(lineage_path)


@router.post("/refresh-universe")
async def refresh_universe(
    body: RefreshUniverseBody,
    base_orchestrator: BatchRefreshOrchestrator = Depends(get_batch_refresh_orchestrator),
    registry: InMemoryJobRegistry = Depends(get_job_registry),
    store: JobStore = Depends(get_job_store),
):
    orchestrator = BatchRefreshOrchestrator(
        market=base_orchestrator._market,  # controlled adaptation for per-run retry settings
        fundamentals=base_orchestrator._fundamentals,
        etl_runner=base_orchestrator._etl_runner,
        job_store=store,
        retry_attempts=body.retry_attempts,
        retry_wait_sec=body.retry_wait_sec,
    )
    run_id = _new_run_id()

    if body.background:
        queue = get_job_queue()
        if settings.job_queue_backend.lower() == "postgres":
            queue.enqueue(
                run_id,
                {
                    "tickers": [t.strip().upper() for t in body.tickers],
                    "force_full": body.force_full,
                    "refresh_quote": body.refresh_quote,
                    "refresh_fundamentals": body.refresh_fundamentals,
                    "run_etl": body.run_etl,
                    "retry_attempts": body.retry_attempts,
                    "retry_wait_sec": body.retry_wait_sec,
                },
            )
            runtime_status = "queued"
        else:
            task = asyncio.create_task(_run_job(orchestrator, body, run_id))
            registry.register(run_id, task)
            runtime_status = "running"
        return {
            "run_id": run_id,
            "status": runtime_status,
            "status_path": str(store.status_path(run_id)),
            "lineage_path": str(store.lineage_path(run_id)),
            "metrics_path": str(store.metrics_path(run_id)),
        }

    status_path, lineage_path = await _run_job(orchestrator, body, run_id)
    return {
        "run_id": run_id,
        "status": "completed",
        "status_path": status_path,
        "lineage_path": lineage_path,
        "metrics_path": str(store.metrics_path(run_id)),
    }


@router.get("/refresh-universe/{run_id}")
async def get_refresh_universe_status(
    run_id: str,
    registry: InMemoryJobRegistry = Depends(get_job_registry),
    store: JobStore = Depends(get_job_store),
):
    payload = await asyncio.to_thread(store.read_status, run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Run id not found")

    handle = registry.get(run_id)
    queue_status = safe_queue_status(run_id)
    if queue_status is not None:
        payload["runtime_status"] = queue_status
    else:
        payload["runtime_status"] = handle.status if handle is not None else "completed"
    return payload


@router.get("/refresh-universe/{run_id}/metrics")
async def get_refresh_universe_metrics(
    run_id: str,
    store: JobStore = Depends(get_job_store),
):
    payload = await asyncio.to_thread(store.read_metrics, run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Metrics for run id not found")
    return payload


@router.get("/refresh-universe/{run_id}/lineage")
async def get_refresh_universe_lineage(
    run_id: str,
    limit: int = Query(100, ge=1, le=10000),
    store: JobStore = Depends(get_job_store),
):
    rows = await asyncio.to_thread(store.read_lineage, run_id, limit)
    if rows is None:
        raise HTTPException(status_code=404, detail="Lineage for run id not found")
    return {
        "run_id": run_id,
        "lineage_path": str(store.lineage_path(run_id)),
        "rows": rows,
    }
