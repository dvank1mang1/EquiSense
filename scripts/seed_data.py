"""
Скрипт для первоначальной загрузки данных по всем тикерам.

Использование:
    python scripts/seed_data.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "JNJ", "V",
]


def seed_ticker(ticker: str) -> None:
    print(f"[{ticker}] Fetching data...")
    # TODO: реализовать после data ingestion
    # from app.data import MarketDataClient, FundamentalDataClient, NewsDataClient
    raise NotImplementedError("Реализуй после data ingestion")


def main():
    for ticker in TICKERS:
        seed_ticker(ticker)
    print("Done.")


if __name__ == "__main__":
    main()
