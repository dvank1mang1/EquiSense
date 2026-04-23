"""
Yahoo Finance / yfinance: warm session + bind yfinance's global YfData singleton.

Yahoo often returns HTTP 429 on chart JSON without prior cookies. Visiting
https://finance.yahoo.com/ on the same TLS client (curl_cffi impersonate) fixes
this for subsequent v8 chart requests that yfinance issues.
"""

from __future__ import annotations

import threading
from typing import Any

from loguru import logger

from app.core.config import settings

_lock = threading.Lock()
_initialized = False


def ensure_yfinance_session() -> None:
    """Idempotent: safe to call from any thread before yfinance network calls."""
    global _initialized
    with _lock:
        if _initialized:
            return
        try:
            from curl_cffi import requests as curl_requests
            from yfinance.data import YfData
        except ImportError as e:
            logger.warning("yfinance session init skipped: {}", e)
            _initialized = True
            return

        session: Any = curl_requests.Session(impersonate="chrome120")
        proxy = (settings.yfinance_proxy_url or "").strip()
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        try:
            warm = session.get("https://finance.yahoo.com/", timeout=25.0)
            logger.info("yfinance Yahoo warm finance.yahoo.com status={}", warm.status_code)
        except Exception as e:
            logger.warning("yfinance Yahoo warm failed (continuing): {}", e)

        # yfinance ships an ancient Chrome/39 UA; Yahoo often returns 429 for it.
        YfData.user_agent_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        }

        # Binds singleton used by all yfinance.Ticker() instances in this process.
        YfData(session=session)
        _initialized = True
