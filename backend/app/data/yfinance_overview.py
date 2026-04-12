"""Подтягивание полей в стиле Alpha Vantage OVERVIEW из yfinance (без ключа AV)."""

from __future__ import annotations

from typing import Any


def yfinance_av_overview_patch(ticker: str) -> dict[str, Any]:
    """
    Возвращает только непустые поля для слияния в сырой overview (кэш/ответ API).
    """
    sym = ticker.strip().upper()
    if not sym:
        return {}
    try:
        import yfinance as yf
    except ImportError:
        return {}

    info: dict[str, Any] = {}
    try:
        raw = yf.Ticker(sym).info
        if isinstance(raw, dict):
            info = raw
    except Exception:
        return {}

    def as_str(v: Any) -> str | None:
        if v is None:
            return None
        return str(v)

    out: dict[str, Any] = {}
    name = info.get("longName") or info.get("shortName")
    if name and str(name).strip():
        out["Name"] = str(name)
    for av_key, yf_key in [
        ("Sector", "sector"),
        ("Industry", "industry"),
        ("MarketCapitalization", "marketCap"),
        ("PERatio", "trailingPE"),
        ("EPS", "trailingEps"),
        ("QuarterlyRevenueGrowthYOY", "revenueGrowth"),
        ("ReturnOnEquityTTM", "returnOnEquity"),
        ("DebtToEquityRatio", "debtToEquity"),
    ]:
        v = info.get(yf_key)
        if v is not None and str(v).strip() not in ("", "None", "nan"):
            s = as_str(v)
            if s is not None:
                out[av_key] = s
    dy = info.get("dividendYield")
    if dy is not None and str(dy).strip() not in ("", "None", "nan"):
        s = as_str(dy)
        if s is not None:
            out["DividendYield"] = s
    return out
