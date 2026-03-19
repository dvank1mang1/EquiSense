import pandas as pd


class SentimentFeatureEngineer:
    """
    Вычисляет sentiment-признаки на основе новостей через FinBERT.

    Признаки:
        - sentiment_score (средний за окно)
        - news_count (количество новостей за окно)
        - positive_ratio, negative_ratio
        - sentiment_momentum (изменение sentiment за N дней)
    """

    def __init__(self, model_name: str = "ProsusAI/finbert"):
        self.model_name = model_name
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        """Lazy loading FinBERT (загружается при первом вызове)."""
        raise NotImplementedError

    def score_text(self, text: str) -> dict:
        """
        Вычислить sentiment одного текста.

        Returns:
            {"label": "positive"|"negative"|"neutral", "score": float}
        """
        raise NotImplementedError

    def score_batch(self, texts: list[str]) -> list[dict]:
        """Batch inference для списка текстов."""
        raise NotImplementedError

    def compute(self, news_list: list[dict], price_dates: pd.DatetimeIndex, window: int = 3) -> pd.DataFrame:
        """
        Агрегировать sentiment по датам для создания временного ряда признаков.

        Args:
            news_list: список новостей с полями title, published_at
            price_dates: даты торговых дней
            window: окно агрегации (дней)

        Returns:
            DataFrame с sentiment-признаками по датам
        """
        raise NotImplementedError
