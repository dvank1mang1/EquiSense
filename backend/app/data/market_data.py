import pandas as pd
from loguru import logger
from app.core.config import settings


class MarketDataClient:
    """
    Клиент для загрузки исторических данных OHLCV.
    Источник: Alpha Vantage API.
    """

    def __init__(self):
        self.api_key = settings.alpha_vantage_api_key

    def get_daily_ohlcv(self, ticker: str, output_size: str = "full") -> pd.DataFrame:
        """
        Загрузить дневные OHLCV данные по тикеру.

        Args:
            ticker: тикер акции (например, 'AAPL')
            output_size: 'compact' (100 дней) или 'full' (до 20 лет)

        Returns:
            DataFrame с колонками: date, open, high, low, close, volume
        """
        raise NotImplementedError

    def get_current_price(self, ticker: str) -> dict:
        """Получить текущую цену акции в реальном времени."""
        raise NotImplementedError

    def update_incremental(self, ticker: str) -> pd.DataFrame:
        """Инкрементальное обновление — только последние N дней."""
        raise NotImplementedError
