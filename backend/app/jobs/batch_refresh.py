from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.contracts.data_providers import FundamentalDataProvider, MarketDataProvider
from app.core.config import settings
from app.domain.exceptions import DataProviderError, UpstreamRateLimitError


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
    error: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _jobs_dir() -> Path:
    # Keep operational job artifacts next to other local data folders.
    return Path(settings.model_dir).resolve().parent / "jobs"


def status_path_for_run(run_id: str) -> Path:
    return _jobs_dir() / f"refresh_status_{run_id}.json"


def lineage_path_for_run(run_id: str) -> Path:
    return _jobs_dir() / f"refresh_lineage_{run_id}.jsonl"


def metrics_path_for_run(run_id: str) -> Path:
    return _jobs_dir() / f"refresh_metrics_{run_id}.json"


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
        *,
        retry_attempts: int = 3,
        retry_wait_sec: float = 2.0,
    ) -> None:
        self._market = market
        self._fundamentals = fundamentals
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
    ) -> tuple[Path, Path]:
        run_id = run_id or datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        jobs_dir = _jobs_dir()
        jobs_dir.mkdir(parents=True, exist_ok=True)
        status_path = status_path_for_run(run_id)
        lineage_path = lineage_path_for_run(run_id)
        metrics_path = metrics_path_for_run(run_id)
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
        status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")

        for ticker in tickers:
            status["in_progress_ticker"] = ticker
            status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
            result = await self._refresh_one(
                ticker=ticker,
                force_full=force_full,
                refresh_quote=refresh_quote,
                refresh_fundamentals=refresh_fundamentals,
            )
            tickers_done += 1
            status["tickers_done"] = tickers_done
            if result.status == "ok":
                success += 1
                status["success"] = success
            else:
                failed += 1
                status["failed"] = failed
            with lineage_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
            status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")

        status["finished_at"] = _utc_now_iso()
        status["in_progress_ticker"] = None
        status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        metrics = {
            "run_id": run_id,
            "duration_sec": round(time.monotonic() - run_started_monotonic, 3),
            "tickers_total": len(tickers),
            "success": success,
            "failed": failed,
            "success_rate": round(success / len(tickers), 4) if tickers else 0.0,
            "finished_at": _utc_now_iso(),
        }
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        logger.bind(event="batch_refresh_run_finished", **metrics).info("Batch refresh run finished")
        return status_path, lineage_path

    async def _refresh_one(
        self,
        *,
        ticker: str,
        force_full: bool,
        refresh_quote: bool,
        refresh_fundamentals: bool,
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
