import pandas as pd
import pytest

from app.data.ohlcv_merge import merge_ohlcv_history


@pytest.mark.unit
def test_merge_concatenates_and_dedupes_by_date() -> None:
    existing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "close": [10.0, 11.0],
            "open": [9.0, 10.5],
            "high": [10.5, 11.5],
            "low": [8.5, 10.0],
            "volume": [100, 110],
        }
    )
    new_rows = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "close": [11.5, 12.0],
            "open": [10.0, 11.0],
            "high": [12.0, 12.5],
            "low": [10.5, 11.5],
            "volume": [120, 130],
        }
    )
    out = merge_ohlcv_history(existing, new_rows)
    assert len(out) == 3
    assert out["date"].is_monotonic_increasing
    # duplicate 2024-01-02 keeps last (new_rows)
    row2 = out[out["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    assert row2["close"] == 11.5


@pytest.mark.unit
def test_merge_empty_existing_returns_new() -> None:
    new_rows = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"]),
            "close": [1.0],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "volume": [1],
        }
    )
    out = merge_ohlcv_history(pd.DataFrame(), new_rows)
    assert len(out) == 1
