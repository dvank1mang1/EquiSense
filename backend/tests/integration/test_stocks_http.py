"""HTTP checks for stocks router."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_get_stock_artifacts_returns_layout() -> None:
    from main import app

    with TestClient(app) as client:
        r = client.get("/api/v1/stocks/ZZZZ/artifacts")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "ZZZZ"
        assert body["raw"]["ohlcv"]["exists"] in (True, False)
        assert body["processed"]["technical"]["exists"] in (True, False)
        assert "path" in body["raw"]["news"]
        assert "data_root" in body
        assert "model_dir" in body


@pytest.mark.integration
def test_get_technical_indicators_returns_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import stocks as stocks_api
    from main import app

    start = datetime(2024, 1, 1)
    rows: list[dict[str, object]] = []
    for i in range(260):
        d = start + timedelta(days=i)
        base = 100.0 + i * 0.5
        rows.append(
            {
                "date": pd.Timestamp(d),
                "open": base - 0.3,
                "high": base + 0.8,
                "low": base - 1.2,
                "close": base,
                "volume": 1_000_000 + i * 10,
            }
        )
    df = pd.DataFrame(rows)

    async def _fake_read_ohlcv(_: str):
        return df

    monkeypatch.setattr(stocks_api, "read_ohlcv_parquet", _fake_read_ohlcv)

    with TestClient(app) as client:
        r = client.get("/api/v1/stocks/AAPL/indicators")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "AAPL"
        assert body.get("rsi") is None or isinstance(body.get("rsi"), float)
        assert body.get("macd") is None or isinstance(body.get("macd"), float)
        assert isinstance(body.get("sma_20"), float)
        assert body.get("volatility") is None or isinstance(body.get("volatility"), float)


@pytest.mark.integration
def test_get_history_prefers_cached_ohlcv_before_upstream_call(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import stocks as stocks_api
    from main import app

    start = datetime(2024, 1, 1)
    rows: list[dict[str, object]] = []
    for i in range(40):
        d = start + timedelta(days=i)
        base = 100.0 + i
        rows.append(
            {
                "date": pd.Timestamp(d),
                "open": base - 0.5,
                "high": base + 0.5,
                "low": base - 1.0,
                "close": base,
                "volume": 1000 + i,
            }
        )
    df = pd.DataFrame(rows)

    async def _fake_read_ohlcv(_: str):
        return df

    monkeypatch.setattr(stocks_api, "read_ohlcv_parquet", _fake_read_ohlcv)

    with TestClient(app) as client:
        r = client.get("/api/v1/stocks/AAPL/history?period=1m")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "AAPL"
        assert body["period"] == "1m"
        assert isinstance(body["candles"], list)
        assert len(body["candles"]) > 0
