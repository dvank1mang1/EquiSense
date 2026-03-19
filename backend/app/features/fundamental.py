import pandas as pd


class FundamentalFeatureEngineer:
    """
    Формирует фундаментальные признаки из данных компании.

    Признаки:
        - pe_ratio
        - eps
        - revenue_growth (квартальный YoY)
        - roe (Return on Equity)
        - debt_to_equity
    """

    def compute(self, overview: dict, income_df: pd.DataFrame | None = None) -> dict:
        """
        Собрать фундаментальные признаки.

        Args:
            overview: dict от Alpha Vantage OVERVIEW
            income_df: квартальный отчёт о прибылях (опционально)

        Returns:
            dict с признаками
        """
        raise NotImplementedError

    def normalize(self, features: dict, reference: dict) -> dict:
        """Нормализация признаков относительно рыночных медиан."""
        raise NotImplementedError
