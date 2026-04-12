from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from loguru import logger

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from app.core.config import settings
from app.core.logging import setup_logging
from app.data.fundamental_data import FundamentalDataClient
from app.data.market_data import MarketDataClient
from app.data.news_data import NewsDataClient
from app.domain.exceptions import BacktestDependencyError, BacktestInputError
from app.etl.pipeline import RawToProcessedETL
from app.features.feature_store import FeatureStore
from app.jobs.backtest_store import BacktestStore
from app.jobs.batch_refresh import BatchRefreshOrchestrator
from app.jobs.queue import PostgresJobQueue
from app.jobs.store import FileJobStore, PostgresJobStore, ResilientJobStore
from app.schemas.backtest import BacktestJobPayload
from app.services.backtesting_service import BacktestingService


def _job_store():
    if settings.job_store_backend.lower() == "postgres":
        return ResilientJobStore(primary=PostgresJobStore(), fallback=FileJobStore())
    return FileJobStore()


async def _run_once(http: httpx.AsyncClient, queue: PostgresJobQueue) -> bool:
    worker_id = f"worker-{os.getpid()}"
    item = await asyncio.to_thread(queue.claim_next, worker_id=worker_id)
    if item is None:
        return False
    payload = item.payload
    job_type = str(payload.get("type", "refresh_universe"))
    job_logger = logger.bind(
        worker_id=worker_id,
        run_id=item.run_id,
        job_type=job_type,
        request_id=item.run_id,
    )
    job_logger.info("Claimed job for processing")

    # Shared adapters
    market_client = MarketDataClient(http=http)
    orchestrator = BatchRefreshOrchestrator(
        market=market_client,
        fundamentals=FundamentalDataClient(http=http),
        etl_runner=RawToProcessedETL(),
        job_store=_job_store(),
        news=NewsDataClient(http=http),
        retry_attempts=int(payload.get("retry_attempts", 3)),
        retry_wait_sec=float(payload.get("retry_wait_sec", 2.0)),
    )
    backtesting_service = BacktestingService(
        market=market_client,
        features=FeatureStore(),
    )
    backtest_store = BacktestStore()
    stop_heartbeat = asyncio.Event()

    async def _heartbeat_loop() -> None:
        while not stop_heartbeat.is_set():
            await asyncio.sleep(max(0.5, settings.worker_heartbeat_sec))
            await asyncio.to_thread(queue.heartbeat, item.run_id, worker_id=worker_id)

    hb_task = asyncio.create_task(_heartbeat_loop())
    try:
        if job_type == "backtest_single":
            bt = BacktestJobPayload.model_validate(payload)
            try:
                resp = await backtesting_service.run_single(
                    ticker=bt.ticker,
                    model=bt.model,
                    start_date=bt.start_date,
                    end_date=bt.end_date,
                    initial_capital=bt.initial_capital,
                )
                await asyncio.to_thread(backtest_store.save, item.run_id, resp)
                await asyncio.to_thread(queue.mark_completed, item.run_id)
                job_logger.info("Backtest job completed")
            except (BacktestDependencyError, BacktestInputError) as e:
                await asyncio.to_thread(queue.mark_failed, item.run_id, str(e))
                job_logger.warning("Backtest job failed: {}", str(e))
        else:
            await orchestrator.run(
                tickers=[str(t).strip().upper() for t in payload.get("tickers", [])],
                run_id=item.run_id,
                force_full=bool(payload.get("force_full", False)),
                refresh_quote=bool(payload.get("refresh_quote", True)),
                refresh_fundamentals=bool(payload.get("refresh_fundamentals", True)),
                run_etl=bool(payload.get("run_etl", False)),
                refresh_news=bool(payload.get("refresh_news", False)),
            )
            await asyncio.to_thread(queue.mark_completed, item.run_id)
            job_logger.info("Refresh job completed")
    except asyncio.CancelledError:
        await asyncio.to_thread(
            queue.requeue_run,
            item.run_id,
            reason="worker shutdown while running; requeued",
        )
        raise
    except Exception as e:  # noqa: BLE001
        await asyncio.to_thread(queue.mark_failed, item.run_id, str(e))
        job_logger.exception("Worker failed: {}", e)
    finally:
        stop_heartbeat.set()
        hb_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await hb_task
    return True


async def _main_loop(poll_sec: float) -> None:
    if settings.job_queue_backend.lower() != "postgres":
        raise SystemExit("JOB_QUEUE_BACKEND must be postgres for worker mode")
    queue = PostgresJobQueue()
    async with httpx.AsyncClient(timeout=120.0) as http:
        try:
            while True:
                requeued = await asyncio.to_thread(
                    queue.requeue_stale_running,
                    stale_after_sec=max(5, settings.job_queue_stale_after_sec),
                )
                if requeued > 0:
                    logger.warning("Requeued {} stale running jobs", requeued)
                had_work = await _run_once(http, queue)
                if not had_work:
                    await asyncio.sleep(poll_sec)
        except asyncio.CancelledError:
            logger.info("Worker loop cancelled; exiting gracefully")
            raise


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Run background job worker loop")
    parser.add_argument("--poll-sec", type=float, default=1.0)
    args = parser.parse_args()
    asyncio.run(_main_loop(args.poll_sec))


if __name__ == "__main__":
    main()
