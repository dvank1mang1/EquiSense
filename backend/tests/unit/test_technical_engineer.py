import numpy as np
import pandas as pd
import pytest

from app.features.constants import LAG_FEATURES, TECHNICAL_FEATURES
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


@pytest.mark.unit
class TestLagFeatures:
    def test_all_lag_columns_present(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        for col in LAG_FEATURES:
            assert col in out.columns, f"missing lag column: {col}"

    def test_lag_columns_count(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        assert len(LAG_FEATURES) == 8

    def test_returns_lag1_equals_shifted_returns(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        expected = out["returns"].shift(1)
        pd.testing.assert_series_equal(
            out["returns_lag1"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_returns_lag5_equals_shifted_returns(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        expected = out["returns"].shift(5)
        pd.testing.assert_series_equal(
            out["returns_lag5"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_volume_change_is_pct_change(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        volume = sample_ohlcv_df.sort_values("date")["volume"].astype(float).reset_index(drop=True)
        expected = volume.pct_change()
        pd.testing.assert_series_equal(
            out["volume_change"].reset_index(drop=True),
            expected,
            check_names=False,
        )

    def test_volume_lag1_equals_shifted_volume_change(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        expected = out["volume_change"].shift(1)
        pd.testing.assert_series_equal(
            out["volume_lag1"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_first_rows_are_nan_for_lag_features(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        assert pd.isna(out["returns_lag1"].iloc[0])
        assert pd.isna(out["returns_lag5"].iloc[0])

    def test_lag_features_finite_after_warmup(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        tail = out.iloc[10:]
        for col in LAG_FEATURES:
            assert tail[col].notna().all(), f"NaN in {col} after warmup"

    def test_output_column_order(self, sample_ohlcv_df: pd.DataFrame) -> None:
        out = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        expected_cols = ["date"] + TECHNICAL_FEATURES + LAG_FEATURES
        assert list(out.columns) == expected_cols
