"""Смоук-тест Alpha Vantage: OHLCV (compact), опционально quote + fundamentals.

Требует ALPHA_VANTAGE_API_KEY в окружении или в backend/.env.
Учитывайте паузы rate limit (~12 с между вызовами на free tier).

Usage:
  uv run python scripts/verify_data_pull.py AAPL
  uv run python scripts/verify_data_pull.py MSFT --full
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(_BACKEND_ROOT / ".env")


async def _run(ticker: str, full: bool) -> None:
    import httpx

    from app.data.fundamental_data import FundamentalDataClient
    from app.data.market_data import MarketDataClient

    if not (os.environ.get("ALPHA_VANTAGE_API_KEY") or "").strip():
        print("Ошибка: задайте ALPHA_VANTAGE_API_KEY (например в backend/.env).", file=sys.stderr)
        sys.exit(1)

    async with httpx.AsyncClient(timeout=120.0) as http:
        market = MarketDataClient(http)
        df = await market.get_daily_ohlcv(ticker, output_size="compact", skip_cache=True)
        n = len(df)
        last = df["date"].iloc[-1] if n else None
        print(f"OK OHLCV compact: rows={n} last_date={last}")

        if not full:
            return

        quote = await market.get_current_price(ticker, skip_cache=True)
        print(f"OK quote price={quote.get('price')} day={quote.get('latest_trading_day')}")

        fund = FundamentalDataClient(http)
        snap = await fund.get_snapshot(ticker, force=True)
        print(f"OK fundamentals Symbol={snap.get('Symbol')} Name={snap.get('Name')!r}")


def main() -> None:
    p = argparse.ArgumentParser(description="Проверка подтягивания данных Alpha Vantage")
    p.add_argument("ticker", nargs="?", default="AAPL")
    p.add_argument(
        "--full",
        action="store_true",
        help="Дополнительно quote и OVERVIEW (ещё 2 вызова API, ~24 с паузы)",
    )
    args = p.parse_args()
    asyncio.run(_run(args.ticker.strip().upper(), args.full))


if __name__ == "__main__":
    main()
