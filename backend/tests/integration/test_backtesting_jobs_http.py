from __future__ import annotations

import asyncio
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.domain.identifiers import ModelId
from app.jobs.backtest_store import BacktestStore
from app.jobs.queue import PostgresJobQueue
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
            }
        )


class _FakeStore:
    def build_combined(self, ticker: str) -> pd.DataFrame:
        _ = ticker
        rows = []
        for d in pd.date_range("2024-01-01", periods=8, freq="D"):
            row = {"date": d}
            for col in (
                "returns",
                "volatility",
                "rsi",
            ):
                row[col] = 0.1
            rows.append(row)
        return pd.DataFrame(rows)

    def exists(self, ticker: str, feature_type: str) -> bool:
        _ = ticker, feature_type
        return True

    def path_for(self, ticker: str, feature_type: str) -> Path:
        return Path(f"/tmp/{ticker}_{feature_type}.parquet")


@pytest.mark.integration
def test_backtest_job_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    from main import app

    class _Model:
        model_id = "model_d"
        feature_set = ["returns", "volatility", "rsi"]

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

    queue = PostgresJobQueue()
    store = BacktestStore()

    try:
        client = TestClient(app)

        r = client.post(
            "/api/v1/backtesting/AAPL/run",
            json={"model": "model_d", "initial_capital": 10000.0},
        )
        assert r.status_code == 200
        body = r.json()
        job_id = body["job_id"]
        assert body["status"] in {"queued", "running"}

        # Simulate worker picking up the job synchronously
        item = queue.claim_next(worker_id="test-worker")
        assert item is not None

        # Directly run the backtest and mark completed
        svc = app.dependency_overrides[get_backtesting_service]()  # type: ignore[call-arg]
        resp = asyncio.run(
            svc.run_single(
                ticker="AAPL",
                model=ModelId.MODEL_D,
                start_date=None,
                end_date=None,
                initial_capital=10000.0,
            )
        )
        store.save(job_id, resp)
        queue.mark_completed(job_id)

        time.sleep(0.1)

        r2 = client.get(f"/api/v1/backtesting/jobs/{job_id}")
        assert r2.status_code == 200
        payload = r2.json()
        assert payload["job_id"] == job_id
        assert payload["status"] == "completed"
        assert payload["result"]["ticker"] == "AAPL"
        assert payload["result"]["model"] == "model_d"

    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_backtest_job_run_validates_model_enum() -> None:
    from main import app

    with TestClient(app) as client:
        r = client.post(
            "/api/v1/backtesting/AAPL/run",
            json={"model": "bad_model_id"},
        )
        assert r.status_code == 422

