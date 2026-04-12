from __future__ import annotations

import asyncio
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from app.domain.exceptions import BacktestDependencyError, BacktestInputError
from app.domain.identifiers import ModelId
from app.jobs.backtest_store import BacktestStore
from app.jobs.queue import get_job_queue, safe_get_job
from app.schemas.backtest import (
    BacktestCompareEntry,
    BacktestCompareResponse,
    BacktestJobPayload,
    BacktestMetrics,
    BacktestResponse,
    BacktestRunJobBody,
)
from app.schemas.common import ErrorResponse
from app.services.backtesting_service import BacktestingService
from app.services.dependencies import get_backtesting_service

router = APIRouter()


_ALLOWED_JOB_STATUSES = {"queued", "running", "completed", "failed"}


def _new_run_id() -> str:
    # Reuse timestamp-based ids similar to jobs.refresh-universe
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


# Static /jobs* must be registered before /{ticker}, otherwise ticker="jobs" steals the path.
@router.get(
    "/jobs",
    summary="List recent backtest jobs",
)
async def list_backtest_jobs(
    ticker: str | None = Query(None),
    model: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """
    List recent backtest jobs using job_queue and filesystem store.

    Uses a simple snapshot of jobs where payload_json.type = 'backtest_single'.
    """
    if status is not None:
        status = status.strip().lower()
        if status not in _ALLOWED_JOB_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status filter: {status!r}. Allowed: {sorted(_ALLOWED_JOB_STATUSES)}",
            )

    queue = get_job_queue()
    # Delegate to the underlying Postgres table using a lightweight custom query.
    rows: list[dict] = []
    if hasattr(queue, "_connect"):
        with queue._connect() as conn:  # type: ignore[attr-defined]
            with conn.cursor() as cur:  # type: ignore[assignment]
                conditions = ["payload_json::json ->> 'type' = 'backtest_single'"]
                params: list[object] = []
                if ticker:
                    conditions.append("payload_json::json ->> 'ticker' = %s")
                    params.append(ticker.strip().upper())
                if model:
                    conditions.append("payload_json::json ->> 'model' = %s")
                    params.append(model)
                if status:
                    conditions.append("status = %s")
                    params.append(status)
                where_sql = " AND ".join(conditions)
                cur.execute(
                    f"""
                    SELECT run_id, status, payload_json, error, created_at, updated_at
                    FROM job_queue
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (*params, limit),
                )
                for run_id, st, payload_json, err, created_at, updated_at in cur.fetchall():
                    try:
                        payload_dict = json.loads(payload_json)
                    except Exception:  # noqa: BLE001
                        payload_dict = {}
                    rows.append(
                        {
                            "job_id": str(run_id),
                            "status": str(st),
                            "ticker": str(payload_dict.get("ticker", "")),
                            "model": str(payload_dict.get("model", "")),
                            "error": str(err) if err is not None else None,
                            "created_at": str(created_at),
                            "updated_at": str(updated_at),
                        }
                    )

    return {"items": rows}


@router.get(
    "/jobs/{job_id}",
    summary="Get backtest job status and result",
)
async def get_backtest_job(job_id: str):
    queue_row = await asyncio.to_thread(safe_get_job, job_id)
    if queue_row is None:
        raise HTTPException(status_code=404, detail="Backtest job not found")

    status = str(queue_row.get("status", "queued"))
    error = queue_row.get("error")

    store = BacktestStore()
    result = await asyncio.to_thread(store.load, job_id)

    if status == "completed":
        if result is None:
            raise HTTPException(status_code=404, detail="Backtest result not found")
        return {"job_id": job_id, "status": "completed", "result": result}

    if status == "failed":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": error or "Backtest job failed",
            "request_id": None,
        }

    return {"job_id": job_id, "status": status}


@router.get(
    "/{ticker}/preflight",
    summary="Check if ticker is ready for local backtesting",
)
async def preflight_backtest_ticker(
    ticker: str,
    service: BacktestingService = Depends(get_backtesting_service),
):
    return await service.preflight(ticker)


@router.get(
    "/{ticker}",
    response_model=BacktestResponse,
    summary="Run model backtest for one ticker",
    responses={
        200: {
            "description": "Backtest completed",
            "content": {
                "application/json": {
                    "example": {
                        "ticker": "AAPL",
                        "model": "model_d",
                        "start_date": "2024-01-01",
                        "end_date": "2024-03-29",
                        "initial_capital": 10000.0,
                        "metrics": {
                            "cumulative_return": 0.1432,
                            "annualized_return": 0.271,
                            "sharpe_ratio": 1.54,
                            "max_drawdown": -0.082,
                            "win_rate": 0.58,
                            "total_trades": 31,
                        },
                        "equity_curve": [
                            {
                                "date": "2024-01-01",
                                "equity": 10000.0,
                                "return_pct": 0.0,
                                "benchmark_equity": 10000.0,
                            }
                        ],
                    }
                }
            },
        },
        404: {"description": "Model artifact missing", "model": ErrorResponse},
        422: {"description": "Invalid date range / empty slice", "model": ErrorResponse},
    },
)
async def run_backtest(
    ticker: str,
    model: ModelId = Query(ModelId.MODEL_D),
    start_date: date | None = Query(None, description="YYYY-MM-DD"),
    end_date: date | None = Query(None, description="YYYY-MM-DD"),
    initial_capital: float = Query(10000.0, ge=100),
    service: BacktestingService = Depends(get_backtesting_service),
):
    sym = ticker.strip().upper()
    logger.info(
        "backtesting.run start ticker={} model={} start={} end={} initial_capital={}",
        sym,
        model.value,
        start_date,
        end_date,
        initial_capital,
    )
    try:
        resp = await service.run_single(
            ticker=ticker,
            model=model,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )
        logger.info(
            "backtesting.run done ticker={} model={} sharpe={} trades={}",
            sym,
            model.value,
            resp.metrics.sharpe_ratio,
            resp.metrics.total_trades,
        )
        return resp
    except BacktestDependencyError as e:
        logger.warning(
            "backtesting.run dependency_error ticker={} model={} err={}", sym, model.value, e
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BacktestInputError as e:
        logger.warning("backtesting.run input_error ticker={} model={} err={}", sym, model.value, e)
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get(
    "/{ticker}/compare",
    response_model=BacktestCompareResponse,
    summary="Compare backtest results across models",
    responses={
        200: {
            "description": "Comparison completed",
            "content": {
                "application/json": {
                    "example": {
                        "ticker": "AAPL",
                        "comparison": {
                            "model_a": {
                                "model": "model_a",
                                "ok": True,
                                "metrics": {
                                    "cumulative_return": 0.102,
                                    "annualized_return": 0.189,
                                    "sharpe_ratio": 1.22,
                                    "max_drawdown": -0.095,
                                    "win_rate": 0.55,
                                    "total_trades": 28,
                                },
                                "error": None,
                            },
                            "model_d": {
                                "model": "model_d",
                                "ok": False,
                                "metrics": None,
                                "error": "Model file not found: data/models/model_d.joblib",
                            },
                        },
                    }
                }
            },
        }
    },
)
async def compare_backtest_models(
    ticker: str,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    initial_capital: float = Query(10000.0, ge=100),
    service: BacktestingService = Depends(get_backtesting_service),
):
    """Сравнение backtesting результатов всех 4 моделей."""
    sym = ticker.strip().upper()
    logger.info(
        "backtesting.compare start ticker={} start={} end={} initial_capital={}",
        sym,
        start_date,
        end_date,
        initial_capital,
    )
    rows = await service.compare_models(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
    comparison = {}
    for k, v in rows.items():
        metrics = None
        if v.metrics is not None:
            metrics = BacktestMetrics(
                cumulative_return=float(v.metrics["cumulative_return"]),
                annualized_return=float(v.metrics["annualized_return"]),
                sharpe_ratio=float(v.metrics["sharpe_ratio"]),
                max_drawdown=float(v.metrics["max_drawdown"]),
                win_rate=float(v.metrics["win_rate"]),
                total_trades=int(v.metrics["total_trades"]),
                turnover=float(v.metrics.get("turnover", 0.0)),
            )
        comparison[k] = BacktestCompareEntry(
            model=v.model,
            ok=v.ok,
            metrics=metrics,
            error=v.error,
        )
    resp = BacktestCompareResponse(
        ticker=ticker.strip().upper(),
        comparison=comparison,
    )
    ok_count = sum(1 for row in comparison.values() if row.ok)
    logger.info(
        "backtesting.compare done ticker={} ok_models={}/{}",
        sym,
        ok_count,
        len(comparison),
    )
    return resp


@router.post(
    "/{ticker}/run",
    summary="Enqueue asynchronous backtest job",
)
async def enqueue_backtest_job(
    ticker: str,
    body: BacktestRunJobBody,
):
    """
    Create a backtest job in the shared PostgresJobQueue.

    Body: { model, start_date?, end_date?, initial_capital? }.
    """
    sym = ticker.strip().upper()
    model = body.model
    start_date = body.start_date
    end_date = body.end_date
    initial_capital = body.initial_capital

    run_id = _new_run_id()
    queue = get_job_queue()
    payload = BacktestJobPayload(
        type="backtest_single",
        run_id=run_id,
        ticker=sym,
        model=model,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
    await asyncio.to_thread(queue.enqueue, run_id, payload.model_dump(mode="json"))
    status = await asyncio.to_thread(queue.status, run_id)
    return {"job_id": run_id, "status": status or "queued"}
