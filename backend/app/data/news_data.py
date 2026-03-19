import pandas as pd
from app.core.config import settings


class NewsDataClient:
    """
    Клиент для загрузки новостей по тикеру.
    Источники: NewsAPI, Finnhub.
    """

    def __init__(self):
        self.news_api_key = settings.news_api_key
        self.finnhub_api_key = settings.finnhub_api_key

    def get_news_by_ticker(self, ticker: str, days_back: int = 30) -> list[dict]:
        """
        Получить новости по тикеру за последние N дней.

        Args:
            ticker: тикер акции
            days_back: количество дней назад

        Returns:
            Список статей: title, source, url, published_at, content
        """
        raise NotImplementedError

    def get_news_from_finnhub(self, ticker: str, from_date: str, to_date: str) -> list[dict]:
        """Получить новости из Finnhub API."""
        raise NotImplementedError
