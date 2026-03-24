"""
Shared fixtures.

Layout mirrors app layers: synthetic market data → feature engineers → persistence.
Paths are always isolated under `tmp_path` to keep tests hermetic.
"""

from __future__ import annotations

from pathlib import Path

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


@pytest.fixture
def isolated_data_root(tmp_path: Path) -> Path:
    """
    Mirrors repo layout: {tmp}/raw/..., {tmp}/processed/..., {tmp}/models optional.
    """
    root = tmp_path / "data"
    (root / "raw" / "ohlcv").mkdir(parents=True)
    (root / "raw" / "fundamentals").mkdir(parents=True)
    (root / "processed").mkdir(parents=True)
    (root / "models").mkdir(parents=True)
    return root


@pytest.fixture
def sample_overview_dict() -> dict:
    """Alpha Vantage OVERVIEW-shaped payload (string values like API)."""
    return {
        "Symbol": "TEST",
        "PERatio": "28.5",
        "EPS": "6.15",
        "QuarterlyRevenueGrowthYOY": "0.082",
        "ReturnOnEquityTTM": "0.147",
        "DebtToEquityRatio": "1.23",
    }
