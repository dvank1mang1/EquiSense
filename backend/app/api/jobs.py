from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from app.contracts.jobs import JobStore
from app.core.config import settings
from app.jobs.batch_refresh import (
    BatchRefreshOrchestrator,
)
from app.jobs.queue import (
    get_job_queue,
    safe_dead_letter_list,
    safe_queue_snapshot,
    safe_queue_status,
    safe_requeue_failed,
)
from app.jobs.registry import InMemoryJobRegistry, get_job_registry
from app.services.dependencies import get_batch_refresh_orchestrator, get_job_store

router = APIRouter()


class RefreshUniverseBody(BaseModel):
    tickers: list[str] = Field(default_factory=list, min_length=1)
    force_full: bool = False
    refresh_quote: bool = True
    refresh_fundamentals: bool = True
    run_etl: bool = False
    refresh_news: bool = Field(
        False,
        description="When run_etl=true, fetch news and refresh raw/news/{TICKER}.json before FinBERT sentiment ETL.",
    )
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
        refresh_news=body.refresh_news,
    )
    return str(status_path), str(lineage_path)


@router.post("/refresh-universe")
async def refresh_universe(
    body: RefreshUniverseBody,
    base_orchestrator: BatchRefreshOrchestrator = Depends(get_batch_refresh_orchestrator),
    registry: InMemoryJobRegistry = Depends(get_job_registry),
    store: JobStore = Depends(get_job_store),
):
    logger.info(
        "jobs.refresh_universe start tickers={} background={} run_etl={} refresh_news={}",
        len(body.tickers),
        body.background,
        body.run_etl,
        body.refresh_news,
    )
    orchestrator = BatchRefreshOrchestrator(
        market=base_orchestrator._market,  # controlled adaptation for per-run retry settings
        fundamentals=base_orchestrator._fundamentals,
        etl_runner=base_orchestrator._etl_runner,
        job_store=store,
        news=base_orchestrator._news,
        retry_attempts=body.retry_attempts,
        retry_wait_sec=body.retry_wait_sec,
    )
    run_id = _new_run_id()

    if body.background:
        queue = get_job_queue()
        if settings.job_queue_backend.lower() == "postgres":
            await asyncio.to_thread(
                queue.enqueue,
                run_id,
                {
                    "tickers": [t.strip().upper() for t in body.tickers],
                    "force_full": body.force_full,
                    "refresh_quote": body.refresh_quote,
                    "refresh_fundamentals": body.refresh_fundamentals,
                    "run_etl": body.run_etl,
                    "refresh_news": body.refresh_news,
                    "retry_attempts": body.retry_attempts,
                    "retry_wait_sec": body.retry_wait_sec,
                    "max_attempts": max(1, settings.job_queue_max_attempts),
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
    logger.info("jobs.refresh_universe done run_id={} mode=sync", run_id)
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
    queue_status = await asyncio.to_thread(safe_queue_status, run_id)
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


@router.get("/worker/health")
async def get_worker_health():
    logger.info("jobs.worker.health check")
    snapshot = await asyncio.to_thread(
        safe_queue_snapshot,
        stale_after_sec=max(5, settings.job_queue_stale_after_sec),
    )
    if snapshot is None:
        return {
            "queue_backend": settings.job_queue_backend,
            "healthy": settings.job_queue_backend.lower() != "postgres",
            "detail": "queue snapshot unavailable",
        }
    return {
        "queue_backend": settings.job_queue_backend,
        "healthy": snapshot.get("stale_running", 0) == 0,
        "snapshot": snapshot,
    }


@router.get("/worker/metrics")
async def get_worker_metrics():
    logger.info("jobs.worker.metrics check")
    snapshot = await asyncio.to_thread(
        safe_queue_snapshot,
        stale_after_sec=max(5, settings.job_queue_stale_after_sec),
    )
    if snapshot is None:
        return {
            "queue_backend": settings.job_queue_backend,
            "available": False,
        }
    queue_depth = int(snapshot.get("queued", 0)) + int(snapshot.get("running", 0))
    failed = int(snapshot.get("failed", 0))
    completed = int(snapshot.get("completed", 0))
    total_finished = failed + completed
    failure_rate = float(failed / total_finished) if total_finished > 0 else 0.0
    dead_letter = int(snapshot.get("dead_letter", 0))
    stale_running = int(snapshot.get("stale_running", 0))
    unhealthy_reasons: list[str] = []
    if stale_running > 0:
        unhealthy_reasons.append("stale_running_jobs")
    if dead_letter > 0:
        unhealthy_reasons.append("dead_letter_jobs")
    return {
        "queue_backend": settings.job_queue_backend,
        "available": True,
        "queue_depth": queue_depth,
        "failure_rate": round(failure_rate, 4),
        "dead_letter": dead_letter,
        "stale_running": stale_running,
        "unhealthy_reasons": unhealthy_reasons,
        "snapshot": snapshot,
    }


@router.get("/worker/dead-letter")
async def list_dead_letter(limit: int = Query(100, ge=1, le=1000)):
    rows = await asyncio.to_thread(safe_dead_letter_list, limit=limit)
    if rows is None:
        return {"queue_backend": settings.job_queue_backend, "rows": []}
    return {
        "queue_backend": settings.job_queue_backend,
        "rows": rows,
        "count": len(rows),
    }


@router.post("/worker/dead-letter/{run_id}/requeue")
async def requeue_dead_letter(run_id: str):
    logger.info("jobs.worker.requeue run_id={}", run_id)
    ok = await asyncio.to_thread(safe_requeue_failed, run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Dead-letter run id not found")
    return {"run_id": run_id, "status": "queued"}
