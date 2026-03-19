import pandas as pd
import numpy as np


class TechnicalFeatureEngineer:
    """
    Вычисляет технические индикаторы и признаки для ML-моделей.

    Признаки:
        - returns (дневная доходность)
        - volatility (скользящее стандартное отклонение)
        - RSI (Relative Strength Index)
        - MACD + Signal + Histogram
        - SMA (20, 50, 200)
        - EMA (12, 26)
        - Bollinger Bands (upper, lower, width)
        - momentum (10-дневный)
    """

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Принять OHLCV DataFrame и добавить все технические признаки.

        Args:
            df: DataFrame с колонками open, high, low, close, volume

        Returns:
            DataFrame с добавленными признаками
        """
        raise NotImplementedError

    def _compute_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        raise NotImplementedError

    def _compute_macd(self, series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        raise NotImplementedError

    def _compute_bollinger_bands(self, series: pd.Series, period: int = 20) -> tuple[pd.Series, pd.Series, pd.Series]:
        raise NotImplementedError
