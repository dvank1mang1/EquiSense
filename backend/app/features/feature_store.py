import pandas as pd
from pathlib import Path
from app.core.config import settings


class FeatureStore:
    """
    Хранит и загружает вычисленные feature sets в формате Parquet.

    Структура файлов:
        data/processed/{ticker}/technical.parquet
        data/processed/{ticker}/fundamental.parquet
        data/processed/{ticker}/sentiment.parquet
        data/processed/{ticker}/combined.parquet
    """

    def __init__(self):
        self.base_path = Path(settings.model_dir).parent / "processed"

    def save(self, ticker: str, feature_type: str, df: pd.DataFrame) -> None:
        """Сохранить features в Parquet."""
        raise NotImplementedError

    def load(self, ticker: str, feature_type: str) -> pd.DataFrame:
        """Загрузить features из Parquet."""
        raise NotImplementedError

    def build_combined(self, ticker: str) -> pd.DataFrame:
        """Объединить все типы признаков в единый DataFrame."""
        raise NotImplementedError

    def exists(self, ticker: str, feature_type: str) -> bool:
        """Проверить, существует ли feature file."""
        raise NotImplementedError
