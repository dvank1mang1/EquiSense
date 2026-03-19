"""
Скрипт для обучения всех ML-моделей.

Использование:
    python scripts/train_models.py --ticker AAPL --ticker MSFT

После реализации всех модулей этот скрипт:
1. Загружает данные
2. Вычисляет features
3. Обучает все 4 модели
4. Сохраняет веса
5. Выводит метрики
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def train_ticker(ticker: str) -> None:
    print(f"[{ticker}] Training all models...")
    # TODO: реализовать после feature engineering
    # from app.data import MarketDataClient, FundamentalDataClient, NewsDataClient
    # from app.features import TechnicalFeatureEngineer, FundamentalFeatureEngineer, SentimentFeatureEngineer
    # from app.models import MODEL_REGISTRY
    raise NotImplementedError("Реализуй после feature engineering")


def main():
    parser = argparse.ArgumentParser(description="Train EquiSense ML models")
    parser.add_argument("--ticker", action="append", default=["AAPL"], help="Тикер для обучения")
    args = parser.parse_args()

    for ticker in args.ticker:
        train_ticker(ticker.upper())


if __name__ == "__main__":
    main()
