"""Batch refresh script with retries, status tracking, and lineage output.

Usage examples:
  uv run python scripts/refresh_universe.py --tickers AAPL,MSFT,NVDA
  uv run python scripts/refresh_universe.py --tickers-file ./tickers.txt --force-full
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

from app.data.fundamental_data import FundamentalDataClient
from app.data.market_data import MarketDataClient
from app.jobs.batch_refresh import BatchRefreshOrchestrator


def _parse_tickers(raw: str) -> list[str]:
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def _read_tickers_file(path: Path) -> list[str]:
    tickers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip().upper()
        if not s or s.startswith("#"):
            continue
        tickers.append(s)
    return tickers


async def _run(args: argparse.Namespace) -> None:
    tickers: list[str] = []
    if args.tickers:
        tickers.extend(_parse_tickers(args.tickers))
    if args.tickers_file:
        tickers.extend(_read_tickers_file(Path(args.tickers_file)))
    tickers = sorted(set(tickers))
    if not tickers:
        raise SystemExit("No tickers provided. Use --tickers or --tickers-file.")

    async with httpx.AsyncClient(timeout=120.0) as http:
        market = MarketDataClient(http)
        fundamentals = FundamentalDataClient(http)
        job = BatchRefreshOrchestrator(
            market=market,
            fundamentals=fundamentals,
            retry_attempts=args.retry_attempts,
            retry_wait_sec=args.retry_wait_sec,
        )
        status_path, lineage_path = await job.run(
            tickers=tickers,
            force_full=args.force_full,
            refresh_quote=not args.skip_quote,
            refresh_fundamentals=not args.skip_fundamentals,
        )
        print(f"Status:  {status_path}")
        print(f"Lineage: {lineage_path}")


def main() -> None:
    p = argparse.ArgumentParser(description="Refresh a ticker universe into local raw cache")
    p.add_argument("--tickers", type=str, default="", help="Comma-separated tickers")
    p.add_argument("--tickers-file", type=str, default="", help="Path to file with one ticker per line")
    p.add_argument("--force-full", action="store_true", help="Force full OHLCV download")
    p.add_argument("--skip-quote", action="store_true", help="Do not refresh GLOBAL_QUOTE")
    p.add_argument(
        "--skip-fundamentals", action="store_true", help="Do not refresh OVERVIEW fundamentals"
    )
    p.add_argument("--retry-attempts", type=int, default=3)
    p.add_argument("--retry-wait-sec", type=float, default=2.0)
    args = p.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

