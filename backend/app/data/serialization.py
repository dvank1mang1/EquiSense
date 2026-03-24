"""Convert DataFrames to JSON-friendly structures for API responses."""

from __future__ import annotations

from typing import Any

import pandas as pd


def ohlcv_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        d = row["date"]
        date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
        rows.append(
            {
                "date": date_str,
                "open": _json_float(row["open"]),
                "high": _json_float(row["high"]),
                "low": _json_float(row["low"]),
                "close": _json_float(row["close"]),
                "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
            }
        )
    return rows


def _json_float(x: Any) -> float | None:
    if x is None or pd.isna(x):
        return None
    return float(x)
