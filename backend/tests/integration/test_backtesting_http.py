from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.services.backtesting_service import BacktestingService
from app.services.dependencies import get_backtesting_service


class _FakeMarket:
    async def get_daily_ohlcv(
        self, ticker: str, output_size: str = "full", *, skip_cache: bool = False
    ):
        _ = ticker, output_size, skip_cache
        return pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=8, freq="D"),
                "close": [100, 101, 102, 101, 103, 104, 103, 105],
                "open": [100, 100, 101, 102, 101, 103, 104, 103],
                "high": [101, 102, 103, 103, 104, 105, 104, 106],
                "low": [99, 100, 101, 100, 102, 103, 102, 104],
                "volume": [1_000_000] * 8,
            }
        )


class _FakeStore:
    def build_combined(self, ticker: str) -> pd.DataFrame:
        _ = ticker
        rows = []
        for d in pd.date_range("2024-01-01", periods=8, freq="D"):
            row = {"date": d}
            # include superset for all model feature sets
            for col in (
                "returns",
                "volatility",
                "rsi",
                "macd",
                "macd_signal",
                "macd_hist",
                "sma_20",
                "sma_50",
                "sma_200",
                "bb_upper",
                "bb_lower",
                "bb_width",
                "momentum",
                "pe_ratio",
                "eps",
                "revenue_growth",
                "roe",
                "debt_to_equity",
                "sentiment_score",
                "news_count",
                "positive_ratio",
                "negative_ratio",
                "sentiment_momentum",
            ):
                row[col] = 0.1
            rows.append(row)
        return pd.DataFrame(rows)

    def exists(self, ticker: str, feature_type: str) -> bool:
        _ = ticker, feature_type
        return True

    def path_for(self, ticker: str, feature_type: str):
        from pathlib import Path

        return Path(f"/tmp/{ticker}_{feature_type}.parquet")


@pytest.mark.integration
def test_run_backtest_http_200(monkeypatch: pytest.MonkeyPatch) -> None:
    from main import app

    class _Model:
        model_id = "model_d"
        feature_set = [
            "returns",
            "volatility",
            "rsi",
            "macd",
            "macd_signal",
            "macd_hist",
            "sma_20",
            "sma_50",
            "sma_200",
            "bb_upper",
            "bb_lower",
            "bb_width",
            "momentum",
            "pe_ratio",
            "eps",
            "revenue_growth",
            "roe",
            "debt_to_equity",
            "sentiment_score",
            "news_count",
            "positive_ratio",
            "negative_ratio",
            "sentiment_momentum",
        ]

        def load(self) -> None:
            pass

        def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
            _ = X
            return np.array([[0.4, 0.6]] * len(X))

        def get_signal(self, p: float) -> str:
            return "Buy" if p >= 0.55 else "Hold"

    monkeypatch.setattr("app.services.backtesting_service.get_model_class", lambda model_id: _Model)
    app.dependency_overrides[get_backtesting_service] = lambda: BacktestingService(
        market=_FakeMarket(),
        features=_FakeStore(),
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backtesting/AAPL?model=model_d")
        assert r.status_code == 200
        payload = r.json()
        assert payload["ticker"] == "AAPL"
        assert payload["model"] == "model_d"
        assert "metrics" in payload
        assert len(payload["equity_curve"]) > 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_compare_backtest_models_http_returns_ok_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    from main import app

    class _Model:
        model_id = "model_d"
        feature_set = [
            "returns",
            "volatility",
            "rsi",
            "macd",
            "macd_signal",
            "macd_hist",
            "sma_20",
            "sma_50",
            "sma_200",
            "bb_upper",
            "bb_lower",
            "bb_width",
            "momentum",
            "pe_ratio",
            "eps",
            "revenue_growth",
            "roe",
            "debt_to_equity",
            "sentiment_score",
            "news_count",
            "positive_ratio",
            "negative_ratio",
            "sentiment_momentum",
        ]

        def load(self) -> None:
            pass

        def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
            _ = X
            return np.array([[0.4, 0.6]] * len(X))

        def get_signal(self, p: float) -> str:
            return "Buy" if p >= 0.55 else "Hold"

    monkeypatch.setattr("app.services.backtesting_service.get_model_class", lambda model_id: _Model)
    app.dependency_overrides[get_backtesting_service] = lambda: BacktestingService(
        market=_FakeMarket(),
        features=_FakeStore(),
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backtesting/AAPL/compare")
        assert r.status_code == 200
        payload = r.json()
        assert payload["ticker"] == "AAPL"
        assert payload["comparison"]["model_a"]["ok"] is True
        assert payload["comparison"]["model_d"]["ok"] is True
    finally:
        app.dependency_overrides.clear()
