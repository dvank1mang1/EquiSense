from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import settings
from app.data.validation import validate_date_column
from app.domain.exceptions import FeatureDataMissingError
from app.domain.identifiers import FeatureSlice
from app.features.constants import FUNDAMENTAL_FEATURES, SENTIMENT_FEATURES, TECHNICAL_FEATURES

_ALLOWED_SLICES = frozenset(
    {
        FeatureSlice.TECHNICAL.value,
        FeatureSlice.FUNDAMENTAL.value,
        FeatureSlice.SENTIMENT.value,
        FeatureSlice.COMBINED.value,
    }
)


class FeatureStore:
    """
    Processed feature sets (Parquet) — отдельное дерево от raw.

    Структура:
        {data_root}/processed/{TICKER}/technical.parquet
        {data_root}/processed/{TICKER}/fundamental.parquet
        data/processed/{TICKER}/sentiment.parquet
        data/processed/{TICKER}/combined.parquet
    """

    def __init__(self, data_root: Path | None = None) -> None:
        self._root = (data_root or Path(settings.model_dir).resolve().parent).resolve()
        self.base_path = self._root / "processed"

    def _ticker_dir(self, ticker: str) -> Path:
        return self.base_path / ticker.strip().upper()

    def _path(self, ticker: str, feature_type: str) -> Path:
        return self._ticker_dir(ticker) / f"{feature_type}.parquet"

    def path_for(self, ticker: str, feature_type: str) -> Path:
        """Absolute path to a processed Parquet artifact."""
        ft = self._validate_slice(feature_type)
        return self._path(ticker, ft)

    def _validate_slice(self, feature_type: str) -> str:
        if feature_type not in _ALLOWED_SLICES:
            raise ValueError(
                f"feature_type must be one of {sorted(_ALLOWED_SLICES)}, got {feature_type!r}"
            )
        return feature_type

    def save(self, ticker: str, feature_type: str, df: pd.DataFrame) -> None:
        """Сохранить features в Parquet."""
        ft = self._validate_slice(feature_type)
        if df.empty:
            raise ValueError("Refusing to save empty DataFrame")
        if "date" in df.columns:
            validate_date_column(df, context=f"processed/{ticker}/{ft}")
        d = self._ticker_dir(ticker)
        d.mkdir(parents=True, exist_ok=True)
        path = self._path(ticker, ft)
        df.to_parquet(path, index=False)

    def load(self, ticker: str, feature_type: str) -> pd.DataFrame:
        """Загрузить features из Parquet."""
        ft = self._validate_slice(feature_type)
        path = self._path(ticker, ft)
        if not path.exists():
            raise FeatureDataMissingError(f"No {ft} features for {ticker}")
        return pd.read_parquet(path)

    def exists(self, ticker: str, feature_type: str) -> bool:
        """Проверить, существует ли feature file."""
        try:
            self._validate_slice(feature_type)
        except ValueError:
            return False
        return self._path(ticker, feature_type).exists()

    def build_combined(self, ticker: str) -> pd.DataFrame:
        """Объединить technical + fundamental + sentiment по дате (left join от technical)."""
        if not self.exists(ticker, FeatureSlice.TECHNICAL.value):
            raise FeatureDataMissingError(f"No technical features for {ticker}")
        tech = self.load(ticker, FeatureSlice.TECHNICAL.value)  # noqa: PD901
        tech["date"] = pd.to_datetime(tech["date"])
        combined = tech.copy()

        if self.exists(ticker, FeatureSlice.FUNDAMENTAL.value):
            fund = self.load(ticker, FeatureSlice.FUNDAMENTAL.value)
            fund["date"] = pd.to_datetime(fund["date"])
            fcols = ["date"] + [c for c in FUNDAMENTAL_FEATURES if c in fund.columns]
            combined = combined.merge(fund[fcols], on="date", how="left")
        else:
            for c in FUNDAMENTAL_FEATURES:
                combined[c] = np.nan

        if self.exists(ticker, FeatureSlice.SENTIMENT.value):
            sent = self.load(ticker, FeatureSlice.SENTIMENT.value)
            sent["date"] = pd.to_datetime(sent["date"])
            scols = ["date"] + [c for c in SENTIMENT_FEATURES if c in sent.columns]
            combined = combined.merge(sent[scols], on="date", how="left")
        else:
            for c in SENTIMENT_FEATURES:
                combined[c] = np.nan

        # Порядок: date, technical, fundamental, sentiment
        ordered = ["date"] + TECHNICAL_FEATURES + FUNDAMENTAL_FEATURES + SENTIMENT_FEATURES
        existing = [c for c in ordered if c in combined.columns]
        rest = [c for c in combined.columns if c not in existing]
        return combined[existing + rest].sort_values("date").reset_index(drop=True)
