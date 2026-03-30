"""Fixtures that require numpy/pandas (only loaded when numeric runtime check passes)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(42)


@pytest.fixture
def sample_ohlcv_df(rng: np.random.Generator) -> pd.DataFrame:
    """
    Synthetic OHLCV with enough rows for SMA-200 + MACD warm-up (≥220 rows).
    """
    n = 260
    dates = pd.date_range("2023-01-03", periods=n, freq="B")
    close = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    high = close + rng.uniform(0.1, 1.0, size=n)
    low = close - rng.uniform(0.1, 1.0, size=n)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.integers(1_000_000, 5_000_000, size=n)
    return pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
