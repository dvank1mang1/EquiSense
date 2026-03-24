"""
Ports: external market, fundamental, and news data.

All I/O-bound methods are async. Implementations use httpx.AsyncClient (see app.state in main).
Pandas-heavy parsing may run in asyncio.to_thread inside adapters when needed.
"""

from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    """Historical and near-real-time OHLCV."""

    async def get_daily_ohlcv(
        self, ticker: str, output_size: str = "full", *, skip_cache: bool = False
    ) -> pd.DataFrame:
        """Daily OHLCV; columns: date, open, high, low, close, volume."""
        ...

    async def get_current_price(self, ticker: str, *, skip_cache: bool = False) -> dict:
        """Quote snapshot for live demo (not HFT)."""
        ...

    async def refresh_ohlcv(self, ticker: str, *, force_full: bool = False) -> pd.DataFrame:
        """Merge compact into stored history or full download when empty / forced."""
        ...

    async def update_incremental(self, ticker: str) -> pd.DataFrame:
        """Fetch a short recent window (e.g. compact daily) to refresh caches."""
        ...


class FundamentalDataProvider(Protocol):
    """Company fundamentals as a snapshot dict (Alpha Vantage OVERVIEW-shaped)."""

    async def get_snapshot(self, ticker: str, *, force: bool = False) -> dict:
        ...


class NewsDataProvider(Protocol):
    """News headlines/bodies for NLP sentiment pipeline."""

    async def get_recent(self, ticker: str, limit: int = 20) -> list[dict]:
        """Each item: title, source, url, published_at (ISO), content (optional)."""
        ...
