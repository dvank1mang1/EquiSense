"""Проверка внешних API по переменным окружения (.env в корне репо и в backend).

Значения ключей не печатаются.

Usage (из каталога backend):
  uv run python scripts/verify_api_keys.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx


def _load_dotenv_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo = Path(__file__).resolve().parents[2]
    backend = Path(__file__).resolve().parents[1]
    load_dotenv(repo / ".env", override=False)
    load_dotenv(backend / ".env", override=True)


async def _check_alpha_vantage(client: httpx.AsyncClient) -> str:
    key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not key:
        return "SKIP (ALPHA_VANTAGE_API_KEY пуст)"
    r = await client.get(
        "https://www.alphavantage.co/query",
        params={"function": "GLOBAL_QUOTE", "symbol": "IBM", "apikey": key},
    )
    if r.status_code != 200:
        return f"FAIL HTTP {r.status_code}"
    data = r.json()
    if "Note" in data or "Information" in data:
        return "FAIL rate limit / лимит free tier (подождите или проверьте ключ)"
    err = data.get("Error Message")
    if err:
        return f"FAIL {str(err)[:120]}"
    gq = data.get("Global Quote") or {}
    if isinstance(gq, dict) and gq.get("05. price"):
        return "OK (GLOBAL_QUOTE)"
    return "FAIL неожиданный ответ"


async def _check_finnhub(client: httpx.AsyncClient) -> str:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return "SKIP (FINNHUB_API_KEY пуст)"
    r = await client.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": "AAPL", "token": key},
    )
    if r.status_code == 401:
        return "FAIL неверный ключ (401)"
    if r.status_code != 200:
        return f"FAIL HTTP {r.status_code}"
    data = r.json()
    if data.get("c") is not None:
        return "OK (quote)"
    return f"FAIL ответ: {str(data)[:200]}"


async def _check_newsapi(client: httpx.AsyncClient) -> str:
    key = os.environ.get("NEWS_API_KEY", "").strip()
    if not key:
        return "SKIP (NEWS_API_KEY пуст)"
    r = await client.get(
        "https://newsapi.org/v2/top-headlines",
        params={"country": "us", "pageSize": 1, "apiKey": key},
    )
    if r.status_code == 401:
        return "FAIL неверный ключ (401)"
    if r.status_code != 200:
        return f"FAIL HTTP {r.status_code}"
    data = r.json()
    if data.get("status") == "ok":
        return "OK (top-headlines)"
    return f"FAIL {data.get('message', str(data)[:200])}"


async def _async_main() -> int:
    _load_dotenv_files()
    print("Проверка ключей (значения не выводятся).")
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        av = await _check_alpha_vantage(client)
        fh = await _check_finnhub(client)
        nw = await _check_newsapi(client)
    print(f"  Alpha Vantage: {av}")
    print(f"  Finnhub:       {fh}")
    print(f"  NewsAPI:       {nw}")
    if any(x.startswith("FAIL") for x in (av, fh, nw)):
        return 1
    return 0


def main() -> None:
    sys.exit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
