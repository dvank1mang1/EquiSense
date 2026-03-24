from __future__ import annotations

from typing import Any

import pandas as pd

from app.domain.exceptions import DataValidationError

_OHLCV_REQUIRED_COLS = frozenset({"date", "open", "high", "low", "close", "volume"})
_FUNDAMENTALS_REQUIRED_KEYS = frozenset({"Symbol"})


def validate_ohlcv_frame(df: pd.DataFrame, *, context: str = "ohlcv") -> None:
    missing = _OHLCV_REQUIRED_COLS.difference(df.columns)
    if missing:
        raise DataValidationError(f"{context}: missing required columns: {sorted(missing)}")
    if df.empty:
        raise DataValidationError(f"{context}: dataframe is empty")
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        try:
            pd.to_datetime(df["date"])
        except Exception as e:  # noqa: BLE001
            raise DataValidationError(f"{context}: 'date' is not parseable datetime") from e


def validate_date_column(df: pd.DataFrame, *, context: str) -> None:
    if "date" not in df.columns:
        raise DataValidationError(f"{context}: missing required column: ['date']")
    if df.empty:
        raise DataValidationError(f"{context}: dataframe is empty")
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        try:
            pd.to_datetime(df["date"])
        except Exception as e:  # noqa: BLE001
            raise DataValidationError(f"{context}: 'date' is not parseable datetime") from e


def validate_fundamentals_snapshot(
    payload: dict[str, Any], *, context: str = "fundamentals"
) -> None:
    missing = [k for k in _FUNDAMENTALS_REQUIRED_KEYS if payload.get(k) in (None, "")]
    if missing:
        raise DataValidationError(f"{context}: missing required keys: {missing}")
