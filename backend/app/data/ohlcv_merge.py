"""Merge incremental OHLCV bars into a stored history (dedupe by date, keep last)."""

from __future__ import annotations

import pandas as pd


def merge_ohlcv_history(existing: pd.DataFrame, new_rows: pd.DataFrame) -> pd.DataFrame:
    if new_rows.empty:
        return existing.sort_values("date").reset_index(drop=True) if len(existing) else new_rows
    if existing.empty:
        return new_rows.sort_values("date").reset_index(drop=True)

    for df in (existing, new_rows):
        if "date" not in df.columns:
            raise ValueError("OHLCV frames must have a 'date' column")

    combined = pd.concat([existing, new_rows], ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.drop_duplicates(subset=["date"], keep="last")
    return combined.sort_values("date").reset_index(drop=True)
