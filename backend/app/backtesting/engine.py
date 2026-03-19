import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class BacktestResult:
    ticker: str
    model_id: str
    start_date: str
    end_date: str
    initial_capital: float
    cumulative_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    equity_curve: pd.DataFrame


class BacktestEngine:
    """
    Симулирует торговую стратегию на основе предсказаний ML-модели.

    Стратегия:
        - Long позиция при сигнале Buy / Strong Buy
        - Выход при сигнале Sell или Hold (в зависимости от настроек)
        - No short selling (для упрощения)

    Метрики:
        - Cumulative Return
        - Annualized Return
        - Sharpe Ratio (risk-free rate = 0)
        - Max Drawdown
        - Win Rate
    """

    def __init__(self, initial_capital: float = 10000.0, risk_free_rate: float = 0.0):
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate

    def run(
        self,
        price_df: pd.DataFrame,
        predictions_df: pd.DataFrame,
        ticker: str,
        model_id: str,
    ) -> BacktestResult:
        """
        Запустить backtesting.

        Args:
            price_df: DataFrame с колонками date, close
            predictions_df: DataFrame с колонками date, probability, signal
            ticker: тикер акции
            model_id: идентификатор модели

        Returns:
            BacktestResult с метриками и equity curve
        """
        raise NotImplementedError

    def _compute_sharpe(self, returns: pd.Series) -> float:
        """Рассчитать Sharpe Ratio (дневные доходности, annualized)."""
        raise NotImplementedError

    def _compute_max_drawdown(self, equity: pd.Series) -> float:
        """Рассчитать максимальную просадку."""
        raise NotImplementedError

    def _compute_win_rate(self, trades: list[dict]) -> float:
        """Рассчитать долю прибыльных сделок."""
        raise NotImplementedError
