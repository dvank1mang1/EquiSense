"""Technical feature engineering — contract vs model_a feature list."""

import numpy as np
import pandas as pd
import pytest

from app.features.constants import TECHNICAL_FEATURES
from app.features.technical import TechnicalFeatureEngineer


@pytest.mark.unit
class TestTechnicalFeatureEngineer:
    def test_compute_adds_all_registered_columns(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        for col in TECHNICAL_FEATURES:
            assert col in out.columns, f"missing feature column: {col}"

    def test_compute_preserves_date_column(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        assert "date" in out.columns
        assert len(out) == len(sample_ohlcv_df)

    def test_compute_sorted_chronologically(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        dates = pd.to_datetime(out["date"])
        assert dates.is_monotonic_increasing

    def test_last_row_has_finite_core_features(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        last = out.iloc[-1]
        for col in ("returns", "rsi", "volatility"):
            assert col in last.index
            assert np.isfinite(last[col]), f"{col} not finite"
