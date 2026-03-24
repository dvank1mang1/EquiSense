from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.jobs.batch_refresh import BatchRefreshOrchestrator
from app.services.dependencies import get_batch_refresh_orchestrator


class _FakeMarket:
    async def refresh_ohlcv(self, ticker: str, *, force_full: bool = False) -> pd.DataFrame:
        _ = ticker, force_full
        return pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-03-24"),
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ]
        )

    async def get_current_price(self, ticker: str, *, skip_cache: bool = False) -> dict:
        _ = ticker, skip_cache
        return {"price": 101.5}


class _FakeFundamentals:
    async def get_snapshot(self, ticker: str, *, force: bool = False) -> dict:
        _ = force
        return {"Symbol": ticker.upper()}


@pytest.mark.integration
def test_refresh_universe_sync_job_and_status_endpoints(tmp_path: Path) -> None:
    from main import app

    old_model_dir = settings.model_dir
    settings.model_dir = str(tmp_path / "models")
    app.dependency_overrides[get_batch_refresh_orchestrator] = lambda: BatchRefreshOrchestrator(
        market=_FakeMarket(),
        fundamentals=_FakeFundamentals(),
        retry_attempts=1,
        retry_wait_sec=0.01,
    )

    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/jobs/refresh-universe",
            json={"tickers": ["AAPL", "MSFT"], "background": False},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["status"] == "completed"
        run_id = payload["run_id"]

        rs = client.get(f"/api/v1/jobs/refresh-universe/{run_id}")
        assert rs.status_code == 200
        status = rs.json()
        assert status["success"] == 2
        assert status["failed"] == 0

        rl = client.get(f"/api/v1/jobs/refresh-universe/{run_id}/lineage")
        assert rl.status_code == 200
        lineage = rl.json()["rows"]
        assert len(lineage) == 2
        assert {row["status"] for row in lineage} == {"ok"}

        rm = client.get(f"/api/v1/jobs/refresh-universe/{run_id}/metrics")
        assert rm.status_code == 200
        metrics = rm.json()
        assert metrics["tickers_total"] == 2
        assert metrics["success"] == 2
    finally:
        settings.model_dir = old_model_dir
        app.dependency_overrides.clear()
