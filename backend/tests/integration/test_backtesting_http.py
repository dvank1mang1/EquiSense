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
                "sentiment_std",
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


class _FakeMarketShouldNotBeCalled:
    async def get_daily_ohlcv(
        self, ticker: str, output_size: str = "full", *, skip_cache: bool = False
    ):
        _ = ticker, output_size, skip_cache
        raise AssertionError("Network fallback must not be called in this test")


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


@pytest.mark.integration
def test_backtest_preflight_http_returns_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    from main import app

    async def _no_cache(ticker: str):
        _ = ticker
        return None

    monkeypatch.setattr(
        "app.services.backtesting_service.read_ohlcv_parquet",
        _no_cache,
    )

    class _StoreNoCombined(_FakeStore):
        def exists(self, ticker: str, feature_type: str) -> bool:
            _ = ticker
            return feature_type != "combined"

    app.dependency_overrides[get_backtesting_service] = lambda: BacktestingService(
        market=_FakeMarket(),
        features=_StoreNoCombined(),
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backtesting/AAPL/preflight")
        assert r.status_code == 200
        payload = r.json()
        assert payload["ticker"] == "AAPL"
        assert payload["ready"] is False
        assert payload["has_cached_ohlcv"] is False
        assert payload["has_combined_features"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_backtest_http_fails_without_cache_when_network_fallback_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from main import app

    old_flag = settings.backtest_allow_network_fallback
    settings.backtest_allow_network_fallback = False

    async def _no_cache(ticker: str):
        _ = ticker
        return None

    monkeypatch.setattr(
        "app.services.backtesting_service.read_ohlcv_parquet",
        _no_cache,
    )

    app.dependency_overrides[get_backtesting_service] = lambda: BacktestingService(
        market=_FakeMarketShouldNotBeCalled(),
        features=_FakeStore(),
    )
    try:
        client = TestClient(app)
        r = client.get("/api/v1/backtesting/AAPL?model=model_d")
        assert r.status_code == 404
        assert "No cached OHLCV for backtest" in r.text
    finally:
        settings.backtest_allow_network_fallback = old_flag
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_backtest_job_status_failed_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from main import app

    monkeypatch.setattr(
        "app.api.backtesting.safe_get_job",
        lambda job_id: {
            "run_id": job_id,
            "status": "failed",
            "payload": {},
            "error": "Combined features are empty",
        },
    )
    monkeypatch.setattr("app.api.backtesting.BacktestStore.load", lambda self, run_id: None)

    with TestClient(app) as client:
        r = client.get("/api/v1/backtesting/jobs/failing-job")
        assert r.status_code == 200
        payload = r.json()
        assert payload["job_id"] == "failing-job"
        assert payload["status"] == "failed"
        assert "error" in payload
