from __future__ import annotations

import argparse
import asyncio
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
from app.data.fundamental_data import FundamentalDataClient
from app.data.market_data import MarketDataClient
from app.etl.pipeline import RawToProcessedETL
from app.jobs.batch_refresh import BatchRefreshOrchestrator
from app.jobs.queue import PostgresJobQueue
from app.jobs.store import FileJobStore, PostgresJobStore, ResilientJobStore


def _job_store():
    if settings.job_store_backend.lower() == "postgres":
        return ResilientJobStore(primary=PostgresJobStore(), fallback=FileJobStore())
    return FileJobStore()


async def _run_once(http: httpx.AsyncClient, queue: PostgresJobQueue) -> bool:
    item = queue.claim_next()
    if item is None:
        return False
    payload = item.payload
    orchestrator = BatchRefreshOrchestrator(
        market=MarketDataClient(http=http),
        fundamentals=FundamentalDataClient(http=http),
        etl_runner=RawToProcessedETL(),
        job_store=_job_store(),
        retry_attempts=int(payload.get("retry_attempts", 3)),
        retry_wait_sec=float(payload.get("retry_wait_sec", 2.0)),
    )
    try:
        await orchestrator.run(
            tickers=[str(t).strip().upper() for t in payload.get("tickers", [])],
            run_id=item.run_id,
            force_full=bool(payload.get("force_full", False)),
            refresh_quote=bool(payload.get("refresh_quote", True)),
            refresh_fundamentals=bool(payload.get("refresh_fundamentals", True)),
            run_etl=bool(payload.get("run_etl", False)),
        )
        queue.mark_completed(item.run_id)
    except Exception as e:  # noqa: BLE001
        queue.mark_failed(item.run_id, str(e))
        logger.exception("Worker failed run_id={} error={}", item.run_id, e)
    return True


async def _main_loop(poll_sec: float) -> None:
    if settings.job_queue_backend.lower() != "postgres":
        raise SystemExit("JOB_QUEUE_BACKEND must be postgres for worker mode")
    queue = PostgresJobQueue()
    async with httpx.AsyncClient(timeout=120.0) as http:
        while True:
            had_work = await _run_once(http, queue)
            if not had_work:
                await asyncio.sleep(poll_sec)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run background job worker loop")
    parser.add_argument("--poll-sec", type=float, default=1.0)
    args = parser.parse_args()
    asyncio.run(_main_loop(args.poll_sec))


if __name__ == "__main__":
    main()
