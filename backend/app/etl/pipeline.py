"""Raw (Parquet/JSON under data/raw) → processed (Parquet under data/processed)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from app.data.persistence import fundamentals_json_path, read_ohlcv_parquet_sync
from app.domain.exceptions import RawDataMissingError
from app.domain.identifiers import FeatureSlice
from app.features.constants import FUNDAMENTAL_FEATURES
from app.features.feature_store import FeatureStore
from app.features.fundamental import FundamentalFeatureEngineer
from app.features.technical import TechnicalFeatureEngineer


class RawToProcessedETL:
    """
    Orchestrates Extract (read raw) → Transform (engineers) → Load (FeatureStore).
    """

    def __init__(self, data_root: Path | None = None) -> None:
        self._root = data_root
        self._store = FeatureStore(data_root=data_root)
        self._technical = TechnicalFeatureEngineer()
        self._fundamental = FundamentalFeatureEngineer()

    def run_technical(self, ticker: str) -> Path:
        sym = ticker.strip().upper()
        raw = read_ohlcv_parquet_sync(sym, root=self._root)
        if raw is None or raw.empty:
            raise RawDataMissingError(
                f"No raw OHLCV at raw/ohlcv/{sym}.parquet under data root"
            )
        feats = self._technical.compute(raw)
        self._store.save(sym, FeatureSlice.TECHNICAL.value, feats)
        return self._store.path_for(sym, FeatureSlice.TECHNICAL.value)

    def run_fundamental(self, ticker: str) -> Path:
        sym = ticker.strip().upper()
        if not self._store.exists(sym, FeatureSlice.TECHNICAL.value):
            raise RawDataMissingError("Run technical ETL first (processed technical missing).")
        json_path = fundamentals_json_path(sym, root=self._root)
        if not json_path.exists():
            raise RawDataMissingError(f"No raw fundamentals JSON at {json_path}")
        overview = json.loads(json_path.read_text(encoding="utf-8"))
        scalar = self._fundamental.compute(overview)
        tech = self._store.load(sym, FeatureSlice.TECHNICAL.value)
        dates = pd.to_datetime(tech["date"])
        daily = pd.DataFrame({"date": dates})
        for k in FUNDAMENTAL_FEATURES:
            v = scalar.get(k)
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                daily[k] = np.nan
            else:
                daily[k] = float(v)
        self._store.save(sym, FeatureSlice.FUNDAMENTAL.value, daily)
        return self._store.path_for(sym, FeatureSlice.FUNDAMENTAL.value)
