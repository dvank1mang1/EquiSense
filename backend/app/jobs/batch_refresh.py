from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from loguru import logger
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.contracts.data_providers import FundamentalDataProvider, MarketDataProvider
from app.contracts.jobs import JobStore
from app.core.config import settings
from app.domain.exceptions import DataProviderError, UpstreamRateLimitError
from app.jobs.store import FileJobStore


class TickerETLRunner(Protocol):
    def run_technical(self, ticker: str) -> Path: ...

    def run_fundamental(self, ticker: str) -> Path: ...


@dataclass
class TickerRefreshResult:
    ticker: str
    status: str
    started_at: str
    finished_at: str
    ohlcv_rows: int | None = None
    last_ohlcv_date: str | None = None
    quote_price: float | None = None
    fundamentals_symbol: str | None = None
    etl_status: str | None = None
    etl_error: str | None = None
    error: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _jobs_dir() -> Path:
    # Keep operational job artifacts next to other local data folders.
    return Path(settings.model_dir).resolve().parent / "jobs"


def status_path_for_run(run_id: str) -> Path:
    return FileJobStore().status_path(run_id)


def lineage_path_for_run(run_id: str) -> Path:
    return FileJobStore().lineage_path(run_id)


def metrics_path_for_run(run_id: str) -> Path:
    return FileJobStore().metrics_path(run_id)


class BatchRefreshOrchestrator:
    """
    Offline job coordinator for multi-ticker refresh.

    Tracks:
    - status file (snapshot during execution)
    - lineage file (one row-like JSON object per ticker)
    """

    def __init__(
        self,
        market: MarketDataProvider,
        fundamentals: FundamentalDataProvider,
        etl_runner: TickerETLRunner | None = None,
        job_store: JobStore | None = None,
        *,
        retry_attempts: int = 3,
        retry_wait_sec: float = 2.0,
    ) -> None:
        self._market = market
        self._fundamentals = fundamentals
        self._etl_runner = etl_runner
        self._store = job_store or FileJobStore()
        self._retry_attempts = retry_attempts
        self._retry_wait_sec = retry_wait_sec

    async def run(
        self,
        tickers: list[str],
        *,
        run_id: str | None = None,
        force_full: bool = False,
        refresh_quote: bool = True,
        refresh_fundamentals: bool = True,
        run_etl: bool = False,
    ) -> tuple[Path, Path]:
        run_id = run_id or datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        status_path = self._store.status_path(run_id)
        lineage_path = self._store.lineage_path(run_id)
        run_started_monotonic = time.monotonic()

        tickers_done = 0
        success = 0
        failed = 0
        status: dict[str, object] = {
            "run_id": run_id,
            "started_at": _utc_now_iso(),
            "tickers_total": len(tickers),
            "tickers_done": tickers_done,
            "success": success,
            "failed": failed,
            "in_progress_ticker": None,
        }
        self._store.write_status(run_id, status)

        for ticker in tickers:
            status["in_progress_ticker"] = ticker
            self._store.write_status(run_id, status)
            result = await self._refresh_one(
                ticker=ticker,
                force_full=force_full,
                refresh_quote=refresh_quote,
                refresh_fundamentals=refresh_fundamentals,
                run_etl=run_etl,
            )
            tickers_done += 1
            status["tickers_done"] = tickers_done
            if result.status == "ok":
                success += 1
                status["success"] = success
            else:
                failed += 1
                status["failed"] = failed
            self._store.append_lineage_row(run_id, asdict(result))
            self._store.write_status(run_id, status)

        status["finished_at"] = _utc_now_iso()
        status["in_progress_ticker"] = None
        self._store.write_status(run_id, status)
        metrics = {
            "run_id": run_id,
            "duration_sec": round(time.monotonic() - run_started_monotonic, 3),
            "tickers_total": len(tickers),
            "success": success,
            "failed": failed,
            "success_rate": round(success / len(tickers), 4) if tickers else 0.0,
            "finished_at": _utc_now_iso(),
        }
        self._store.write_metrics(run_id, metrics)
        logger.bind(event="batch_refresh_run_finished", **metrics).info(
            "Batch refresh run finished"
        )
        return status_path, lineage_path

    async def _refresh_one(
        self,
        *,
        ticker: str,
        force_full: bool,
        refresh_quote: bool,
        refresh_fundamentals: bool,
        run_etl: bool,
    ) -> TickerRefreshResult:
        started = _utc_now_iso()
        started_monotonic = time.monotonic()

        async def _op() -> TickerRefreshResult:
            ohlcv = await self._market.refresh_ohlcv(ticker, force_full=force_full)
            quote_price: float | None = None
            fundamentals_symbol: str | None = None
            if refresh_quote:
                quote = await self._market.get_current_price(ticker, skip_cache=True)
                maybe_price = quote.get("price")
                if isinstance(maybe_price, (float, int)):
                    quote_price = float(maybe_price)
            if refresh_fundamentals:
                snap = await self._fundamentals.get_snapshot(ticker, force=True)
                symbol = snap.get("Symbol")
                if isinstance(symbol, str):
                    fundamentals_symbol = symbol

            etl_status: str | None = None
            etl_error: str | None = None
            if run_etl:
                if self._etl_runner is None:
                    etl_status = "skipped"
                    etl_error = "etl runner is not configured"
                else:
                    try:
                        await asyncio.to_thread(self._etl_runner.run_technical, ticker)
                        await asyncio.to_thread(self._etl_runner.run_fundamental, ticker)
                        etl_status = "ok"
                    except Exception as etl_exc:  # noqa: BLE001
                        etl_status = "error"
                        etl_error = str(etl_exc)

            last_date: str | None = None
            if len(ohlcv):
                last_date = str(ohlcv["date"].iloc[-1])[:10]
            return TickerRefreshResult(
                ticker=ticker.upper(),
                status="ok",
                started_at=started,
                finished_at=_utc_now_iso(),
                ohlcv_rows=int(len(ohlcv)),
                last_ohlcv_date=last_date,
                quote_price=quote_price,
                fundamentals_symbol=fundamentals_symbol,
                etl_status=etl_status,
                etl_error=etl_error,
            )

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._retry_attempts),
                wait=wait_fixed(self._retry_wait_sec),
                retry=retry_if_exception_type((UpstreamRateLimitError, DataProviderError)),
                reraise=True,
            ):
                with attempt:
                    result = await _op()
                    logger.bind(
                        event="batch_refresh_ticker_ok",
                        ticker=ticker.upper(),
                        duration_sec=round(time.monotonic() - started_monotonic, 3),
                    ).info("Ticker refresh succeeded")
                    return result
            raise RuntimeError("Retrying loop ended without result")
        except Exception as e:  # keep per-ticker failures isolated in batch mode
            await asyncio.sleep(0)
            logger.bind(
                event="batch_refresh_ticker_error",
                ticker=ticker.upper(),
                duration_sec=round(time.monotonic() - started_monotonic, 3),
                error=str(e),
            ).warning("Ticker refresh failed")
            return TickerRefreshResult(
                ticker=ticker.upper(),
                status="error",
                started_at=started,
                finished_at=_utc_now_iso(),
                error=str(e),
            )
