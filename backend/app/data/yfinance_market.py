"""OHLCV и котировка из yfinance — fallback, когда Alpha Vantage уперся в квоту/лимит."""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from app.core.config import settings
from app.data.utils import normalize_ticker
from app.data.yfinance_session import ensure_yfinance_session
from app.domain.exceptions import DataProviderError


def _ticker(sym: str) -> Any:
    import yfinance as yf

    ensure_yfinance_session()
    return yf.Ticker(sym)


def fetch_daily_ohlcv_yfinance(ticker: str, *, output_size: str = "full") -> pd.DataFrame:
    sym = normalize_ticker(ticker)
    if output_size not in ("full", "compact"):
        raise DataProviderError("output_size must be 'full' or 'compact'")
    try:
        yf_ticker = _ticker(sym)
    except ImportError as e:
        raise DataProviderError("yfinance is not installed") from e

    period = "1y" if output_size == "compact" else "max"
    proxy_url = (settings.yfinance_proxy_url or "").strip() or None
    hist = yf_ticker.history(
        period=period, interval="1d", auto_adjust=True, actions=False, proxy=proxy_url
    )
    if hist is None or hist.empty:
        raise DataProviderError(f"yfinance: no OHLCV for {sym}")

    df = hist.reset_index()
    date_col = df.columns[0]
    vol = pd.to_numeric(df.get("Volume", 0), errors="coerce").fillna(0.0).clip(lower=0)
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df[date_col], errors="coerce"),
            "open": pd.to_numeric(df["Open"], errors="coerce"),
            "high": pd.to_numeric(df["High"], errors="coerce"),
            "low": pd.to_numeric(df["Low"], errors="coerce"),
            "close": pd.to_numeric(df["Close"], errors="coerce"),
            "volume": vol.round().clip(lower=0).fillna(0.0).astype(int),
        }
    )
    out = out.dropna(subset=["date", "close"])
    if out.empty:
        raise DataProviderError(f"yfinance: OHLCV empty after cleaning for {sym}")
    out = out.sort_values("date").reset_index(drop=True)
    if output_size == "compact":
        out = out.tail(min(120, len(out))).reset_index(drop=True)
    logger.info("yfinance OHLCV fallback ticker={} rows={} period={}", sym, len(out), period)
    return out


def fetch_quote_yfinance(ticker: str) -> dict[str, Any]:
    sym = normalize_ticker(ticker)
    try:
        yf_ticker = _ticker(sym)
    except ImportError as e:
        raise DataProviderError("yfinance is not installed") from e

    proxy_url = (settings.yfinance_proxy_url or "").strip() or None
    hist = yf_ticker.history(
        period="5d", interval="1d", auto_adjust=True, actions=False, proxy=proxy_url
    )
    if hist is None or hist.empty:
        raise DataProviderError(f"yfinance: no recent bars for {sym}")

    close = hist["Close"]
    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) >= 2 else price
    idx = hist.index[-1]
    latest = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]

    o = float(hist["Open"].iloc[-1]) if "Open" in hist.columns else None
    h = float(hist["High"].iloc[-1]) if "High" in hist.columns else None
    low = float(hist["Low"].iloc[-1]) if "Low" in hist.columns else None
    vol: int | None = None
    if "Volume" in hist.columns:
        vr = hist["Volume"].iloc[-1]
        if pd.notna(vr):
            vol = int(float(vr))

    chg = price - prev
    chg_pct = (100.0 * chg / prev) if prev else None
    data: dict[str, Any] = {
        "symbol": sym,
        "open": o,
        "high": h,
        "low": low,
        "price": price,
        "volume": vol,
        "latest_trading_day": latest,
        "previous_close": prev,
        "change": chg,
        "change_percent": f"{chg_pct:.4f}" if chg_pct is not None else None,
    }
    logger.info("yfinance quote fallback ticker={} price={}", sym, price)
    return data
