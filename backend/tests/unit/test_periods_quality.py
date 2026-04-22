import pandas as pd

from app.data.periods import (
    ohlcv_series_quality_hints,
    ohlcv_tail_by_period,
    sanitize_ohlcv_dataframe,
)


def test_sanitize_dedupes_same_calendar_day() -> None:
    df = pd.DataFrame(
        {
            "date": [
                pd.Timestamp("2025-01-02 10:00:00", tz="UTC"),
                pd.Timestamp("2025-01-02 18:00:00", tz="UTC"),
            ],
            "close": [100.0, 101.0],
            "open": [99.0, 100.0],
            "high": [101.0, 102.0],
            "low": [98.0, 99.0],
            "volume": [1, 2],
        }
    )
    out = sanitize_ohlcv_dataframe(df)
    assert len(out) == 1
    assert float(out["close"].iloc[0]) == 101.0


def test_quality_hints_sparse() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2026-10-15"]),
            "close": [100.0, 110.0],
        }
    )
    hints = ohlcv_series_quality_hints(df)
    assert "sparse_daily_bars" in hints
    assert "long_calendar_gaps" in hints


def test_ohlcv_tail_by_period_uses_calendar_window_not_row_budget() -> None:
    """2y must not stitch unrelated history before a gap just to reach 504 rows."""
    dates = list(pd.date_range("2023-07-01", "2025-01-10", freq="B")) + list(
        pd.date_range("2026-01-02", "2026-04-10", freq="B")
    )
    df = pd.DataFrame({"date": dates, "close": range(len(dates))})
    sliced = ohlcv_tail_by_period(df, "2y")
    assert sliced["date"].min() >= pd.Timestamp("2024-04-10")
    assert len(sliced) < len(dates)


def test_ohlcv_tail_by_period_max_returns_all_sorted() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-02-01", "2025-01-02"]),
            "close": [2.0, 1.0],
        }
    )
    out = ohlcv_tail_by_period(df, "max")
    assert list(out["close"]) == [1.0, 2.0]
