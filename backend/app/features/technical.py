import numpy as np
import pandas as pd

from app.features.constants import TECHNICAL_FEATURES


class TechnicalFeatureEngineer:
    """
    Вычисляет технические индикаторы и признаки для ML-моделей.
    Выход содержит колонку `date` + ровно TECHNICAL_FEATURES (совместимость с Model A).
    """

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"OHLCV DataFrame missing columns: {missing}")

        out = df.copy()
        if "date" not in out.columns:
            raise ValueError("Expected 'date' column in OHLCV frame")
        out["date"] = pd.to_datetime(out["date"])
        out = out.sort_values("date").reset_index(drop=True)

        close = out["close"].astype(float)

        out["returns"] = close.pct_change()
        out["volatility"] = out["returns"].rolling(window=20, min_periods=1).std()
        out["rsi"] = self._compute_rsi(close, 14)
        macd, sig, hist = self._compute_macd(close)
        out["macd"] = macd
        out["macd_signal"] = sig
        out["macd_hist"] = hist
        out["sma_20"] = close.rolling(20, min_periods=1).mean()
        out["sma_50"] = close.rolling(50, min_periods=1).mean()
        out["sma_200"] = close.rolling(200, min_periods=1).mean()
        upper, lower, width = self._compute_bollinger_bands(close, 20)
        out["bb_upper"] = upper
        out["bb_lower"] = lower
        out["bb_width"] = width
        out["momentum"] = close - close.shift(10)

        cols = ["date"] + TECHNICAL_FEATURES
        return out[cols]

    def _compute_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)
        avg_gain = gain.rolling(period, min_periods=1).mean()
        avg_loss = loss.rolling(period, min_periods=1).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def _compute_macd(self, series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal
        return macd_line, signal, hist

    def _compute_bollinger_bands(
        self, series: pd.Series, period: int = 20
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        mid = series.rolling(period, min_periods=1).mean()
        std = series.rolling(period, min_periods=1).std()
        upper = mid + 2 * std
        lower = mid - 2 * std
        width = (upper - lower) / mid.replace(0, np.nan)
        return upper, lower, width
