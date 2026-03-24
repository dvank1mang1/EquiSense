"""Processed layer (Parquet) — separate tree from raw."""

import numpy as np
import pandas as pd
import pytest

from app.domain.identifiers import FeatureSlice
from app.features.constants import FUNDAMENTAL_FEATURES, SENTIMENT_FEATURES
from app.features.feature_store import FeatureStore


@pytest.mark.unit
class TestFeatureStore:
    def test_save_load_roundtrip_technical(
        self, isolated_data_root, sample_ohlcv_df: pd.DataFrame
    ) -> None:
        store = FeatureStore(data_root=isolated_data_root)
        df = sample_ohlcv_df.copy()
        df["returns"] = df["close"].pct_change()
        store.save("test", FeatureSlice.TECHNICAL.value, df)
        loaded = store.load("test", FeatureSlice.TECHNICAL.value)
        assert len(loaded) == len(df)
        assert "date" in loaded.columns

    def test_exists_after_save(self, isolated_data_root) -> None:
        store = FeatureStore(data_root=isolated_data_root)
        df = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=3, freq="D"), "x": [1, 2, 3]}
        )
        assert not store.exists("ab", FeatureSlice.TECHNICAL.value)
        store.save("ab", FeatureSlice.TECHNICAL.value, df)
        assert store.exists("ab", FeatureSlice.TECHNICAL.value)

    def test_invalid_feature_type_raises(self, isolated_data_root) -> None:
        store = FeatureStore(data_root=isolated_data_root)
        df = pd.DataFrame({"a": [1]})
        with pytest.raises(ValueError, match="feature_type"):
            store.save("x", "not_a_slice", df)

    def test_build_combined_aligns_on_date_and_fills_missing_groups(
        self, isolated_data_root
    ) -> None:
        store = FeatureStore(data_root=isolated_data_root)
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        tech = pd.DataFrame(
            {
                "date": dates,
                "close": np.linspace(100, 110, 10),
                "rsi": np.linspace(40, 60, 10),
            }
        )
        store.save("zz", FeatureSlice.TECHNICAL.value, tech)
        fund = pd.DataFrame(
            {
                "date": dates,
                **{k: 1.0 for k in FUNDAMENTAL_FEATURES},
            }
        )
        store.save("zz", FeatureSlice.FUNDAMENTAL.value, fund)
        sent = pd.DataFrame(
            {
                "date": dates,
                **{k: 0.0 for k in SENTIMENT_FEATURES},
            }
        )
        store.save("zz", FeatureSlice.SENTIMENT.value, sent)

        combined = store.build_combined("zz")
        assert "date" in combined.columns
        assert "rsi" in combined.columns
        for k in FUNDAMENTAL_FEATURES:
            assert k in combined.columns
        for k in SENTIMENT_FEATURES:
            assert k in combined.columns
        assert len(combined) == len(dates)
