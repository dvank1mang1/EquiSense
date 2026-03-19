import pandas as pd
from app.core.config import settings


class FundamentalDataClient:
    """
    Клиент для загрузки фундаментальных показателей компаний.
    Источник: Alpha Vantage (OVERVIEW endpoint).
    """

    def __init__(self):
        self.api_key = settings.alpha_vantage_api_key

    def get_company_overview(self, ticker: str) -> dict:
        """
        Получить обзор компании: P/E, EPS, ROE, Debt/Equity, Market Cap.

        Returns:
            dict с фундаментальными метриками
        """
        raise NotImplementedError

    def get_income_statement(self, ticker: str) -> pd.DataFrame:
        """Получить данные отчёта о прибылях и убытках (квартальный)."""
        raise NotImplementedError

    def get_balance_sheet(self, ticker: str) -> pd.DataFrame:
        """Получить баланс компании."""
        raise NotImplementedError
