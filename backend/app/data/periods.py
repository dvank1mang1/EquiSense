"""UI period presets for OHLCV history: calendar windows from the last bar."""

from __future__ import annotations

import pandas as pd

# Approximate trading-day counts (documentation / rough expectations only).
# History slicing uses calendar offsets from max(date), not tail(n), so gaps in
# Parquet do not pull in unrelated older rows just to fill a row budget.
PERIOD_ROWS: dict[str, int] = {
    "1m": 22,
    "3m": 66,
    "6m": 126,
    "1y": 252,
    "2y": 504,
    "max": 10**9,
}

_PERIOD_OFFSETS: dict[str, pd.DateOffset] = {
    "1m": pd.DateOffset(months=1),
    "3m": pd.DateOffset(months=3),
    "6m": pd.DateOffset(months=6),
    "1y": pd.DateOffset(years=1),
    "2y": pd.DateOffset(years=2),
}


def ohlcv_tail_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Return rows whose ``date`` falls in [last_date − preset, last_date] (inclusive).

    ``max`` returns the full series (still sorted). Unknown ``period`` falls back to
    the legacy last-252-rows behaviour for resilience.
    """
    if df.empty:
        return df
    out = df.sort_values("date").reset_index(drop=True)
    if period == "max":
        return out
    off = _PERIOD_OFFSETS.get(period)
    if off is None:
        n = PERIOD_ROWS.get(period, PERIOD_ROWS["1y"])
        return out.tail(n).reset_index(drop=True)
    end = out["date"].max()
    if pd.isna(end):
        return out.iloc[0:0]
    start = pd.Timestamp(end) - off
    mask = (out["date"] >= start) & (out["date"] <= end)
    return out.loc[mask].reset_index(drop=True)


def sanitize_ohlcv_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Naive calendar dates at midnight, drop invalid rows, dedupe by date.

    Mixed tz-aware / naive ``date`` values (e.g. yfinance + merges) otherwise
    produce duplicate calendar days or odd sorting; very sparse files then draw
    as an almost straight line on long ranges in Plotly.
    """
    if df.empty or "date" not in df.columns:
        return df
    out = df.copy()
    ts = pd.to_datetime(out["date"], errors="coerce")
    if pd.api.types.is_datetime64tz_dtype(ts.dtype):
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    out["date"] = ts.dt.normalize()
    if "close" in out.columns:
        out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["date", "close"]).sort_values("date")
    out = out.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    return out


def ohlcv_series_quality_hints(df: pd.DataFrame) -> list[str]:
    """Human-facing hint codes for sparse / flat price caches."""
    hints: list[str] = []
    if df.empty or len(df) < 2:
        return hints
    d = df.sort_values("date").reset_index(drop=True)
    span_days = int((d["date"].iloc[-1] - d["date"].iloc[0]).days)
    gaps = d["date"].diff().dt.days
    max_gap = float(gaps.iloc[1:].max()) if len(gaps) > 1 else 0.0
    if span_days >= 45 and max_gap > 14:
        hints.append("long_calendar_gaps")
    if span_days >= 90 and len(d) < max(15, span_days // 20):
        hints.append("sparse_daily_bars")
    close = pd.to_numeric(d.get("close"), errors="coerce")
    if len(close.dropna()) >= 20 and close.nunique(dropna=True) <= 1:
        hints.append("constant_close")
    return hints
