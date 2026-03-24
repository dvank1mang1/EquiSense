"""Raw → processed ETL (technical first; optional fundamental/sentiment)."""

from pathlib import Path

import pandas as pd
import pytest

from app.domain.exceptions import RawDataMissingError
from app.domain.identifiers import FeatureSlice
from app.etl.pipeline import RawToProcessedETL
from app.features.feature_store import FeatureStore


@pytest.mark.unit
class TestRawToProcessedETL:
    def test_run_technical_raises_when_raw_parquet_missing(
        self, isolated_data_root: Path
    ) -> None:
        etl = RawToProcessedETL(data_root=isolated_data_root)
        with pytest.raises(RawDataMissingError):
            etl.run_technical("missing")

    def test_run_technical_writes_processed_technical_parquet(
        self, isolated_data_root: Path, sample_ohlcv_df: pd.DataFrame
    ) -> None:
        raw_path = isolated_data_root / "raw" / "ohlcv" / "AAA.parquet"
        sample_ohlcv_df.to_parquet(raw_path, index=False)

        etl = RawToProcessedETL(data_root=isolated_data_root)
        out_path = etl.run_technical("AAA")
        assert out_path.exists()
        store = FeatureStore(data_root=isolated_data_root)
        assert store.exists("AAA", FeatureSlice.TECHNICAL.value)
        df = pd.read_parquet(out_path)
        assert "rsi" in df.columns

    def test_run_technical_idempotent_row_count_stable(
        self, isolated_data_root: Path, sample_ohlcv_df: pd.DataFrame
    ) -> None:
        raw_path = isolated_data_root / "raw" / "ohlcv" / "BBB.parquet"
        sample_ohlcv_df.to_parquet(raw_path, index=False)
        etl = RawToProcessedETL(data_root=isolated_data_root)
        etl.run_technical("BBB")
        etl.run_technical("BBB")
        store = FeatureStore(data_root=isolated_data_root)
        df = store.load("BBB", FeatureSlice.TECHNICAL.value)
        assert len(df) == len(sample_ohlcv_df)

    def test_run_fundamental_from_raw_json(
        self,
        isolated_data_root: Path,
        sample_ohlcv_df: pd.DataFrame,
        sample_overview_dict: dict,
    ) -> None:
        sample_ohlcv_df.to_parquet(
            isolated_data_root / "raw" / "ohlcv" / "CCC.parquet", index=False
        )
        import json

        p = isolated_data_root / "raw" / "fundamentals" / "CCC.json"
        p.write_text(json.dumps(sample_overview_dict), encoding="utf-8")

        etl = RawToProcessedETL(data_root=isolated_data_root)
        etl.run_technical("CCC")
        etl.run_fundamental("CCC")
        store = FeatureStore(data_root=isolated_data_root)
        assert store.exists("CCC", FeatureSlice.FUNDAMENTAL.value)
