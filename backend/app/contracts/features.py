"""Port for persisted engineered features (Parquet / DB / future online store)."""

from typing import Protocol

import pandas as pd


class FeatureStorePort(Protocol):
    """Read/write processed feature tables per ticker and logical slice."""

    def save(self, ticker: str, feature_type: str, df: pd.DataFrame) -> None:
        ...

    def load(self, ticker: str, feature_type: str) -> pd.DataFrame:
        ...

    def build_combined(self, ticker: str) -> pd.DataFrame:
        """Join technical + fundamental + sentiment into model-ready frame."""
        ...

    def exists(self, ticker: str, feature_type: str) -> bool:
        ...
