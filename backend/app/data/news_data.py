"""News: Finnhub company-news (preferred) or NewsAPI everything — async HTTP."""

from __future__ import annotations

from datetime import UTC, date, timedelta
from typing import Any

import httpx
from loguru import logger

from app.core.config import settings
from app.data.utils import normalize_ticker
from app.domain.exceptions import DataProviderError, UpstreamRateLimitError

FINNHUB_BASE = "https://finnhub.io/api/v1"
NEWSAPI_BASE = "https://newsapi.org/v2"


class NewsDataClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._finnhub = (settings.finnhub_api_key or "").strip()
        self._newsapi = (settings.news_api_key or "").strip()

    async def get_recent(self, ticker: str, limit: int = 20) -> list[dict]:
        sym = normalize_ticker(ticker)
        if self._finnhub:
            return await self._from_finnhub(sym, limit)
        if self._newsapi:
            return await self._from_newsapi(sym, limit)
        logger.warning("No FINNHUB_API_KEY or NEWS_API_KEY — returning empty news for {}", sym)
        return []

    async def _from_finnhub(self, sym: str, limit: int) -> list[dict]:
        to_d = date.today()
        from_d = to_d - timedelta(days=30)
        params: dict[str, Any] = {
            "symbol": sym,
            "from": from_d.isoformat(),
            "to": to_d.isoformat(),
            "token": self._finnhub,
        }
        try:
            r = await self._http.get(f"{FINNHUB_BASE}/company-news", params=params)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise UpstreamRateLimitError("Finnhub rate limit") from e
            raise DataProviderError(f"Finnhub HTTP {e.response.status_code}") from e
        raw = r.json()
        if not isinstance(raw, list):
            raise DataProviderError(f"Unexpected Finnhub response: {type(raw)}")

        out: list[dict] = []
        for item in raw[:limit]:
            ts = item.get("datetime")
            if isinstance(ts, int | float):
                from datetime import datetime

                published = datetime.fromtimestamp(ts, tz=UTC).isoformat()
            else:
                published = ""
            out.append(
                {
                    "title": item.get("headline") or "",
                    "source": item.get("source") or "unknown",
                    "url": item.get("url") or "",
                    "published_at": published,
                    "content": (item.get("summary") or "")[:2000],
                }
            )
        return out

    async def _from_newsapi(self, sym: str, limit: int) -> list[dict]:
        params: dict[str, str | int] = {
            "q": sym,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": min(limit, 100),
            "apiKey": self._newsapi,
        }
        try:
            r = await self._http.get(f"{NEWSAPI_BASE}/everything", params=params)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise UpstreamRateLimitError("NewsAPI rate limit") from e
            raise DataProviderError(f"NewsAPI HTTP {e.response.status_code}") from e
        payload = r.json()
        if payload.get("status") != "ok":
            raise DataProviderError(payload.get("message") or "NewsAPI error")

        articles = payload.get("articles") or []
        out: list[dict] = []
        for a in articles[:limit]:
            out.append(
                {
                    "title": a.get("title") or "",
                    "source": (a.get("source") or {}).get("name") or "unknown",
                    "url": a.get("url") or "",
                    "published_at": a.get("publishedAt") or "",
                    "content": (a.get("description") or "")[:2000],
                }
            )
        return out
