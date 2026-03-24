"""Port for strategy simulation over historical prices + model outputs."""

from typing import Protocol

import pandas as pd

from app.backtesting.engine import BacktestResult


class BacktestRunner(Protocol):
    def run(
        self,
        price_df: pd.DataFrame,
        predictions_df: pd.DataFrame,
        ticker: str,
        model_id: str,
    ) -> BacktestResult: ...
