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


class _FakeETL:
    def run_technical(self, ticker: str):
        _ = ticker
        return Path("/tmp/tech.parquet")

    def run_fundamental(self, ticker: str):
        _ = ticker
        return Path("/tmp/fund.parquet")


@pytest.mark.integration
def test_refresh_universe_sync_job_and_status_endpoints(tmp_path: Path) -> None:
    from main import app

    old_model_dir = settings.model_dir
    settings.model_dir = str(tmp_path / "models")
    app.dependency_overrides[get_batch_refresh_orchestrator] = lambda: BatchRefreshOrchestrator(
        market=_FakeMarket(),
        fundamentals=_FakeFundamentals(),
        etl_runner=_FakeETL(),
        retry_attempts=1,
        retry_wait_sec=0.01,
    )

    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/jobs/refresh-universe",
            json={"tickers": ["AAPL", "MSFT"], "background": False, "run_etl": True},
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
        assert {row["etl_status"] for row in lineage} == {"ok"}

        rm = client.get(f"/api/v1/jobs/refresh-universe/{run_id}/metrics")
        assert rm.status_code == 200
        metrics = rm.json()
        assert metrics["tickers_total"] == 2
        assert metrics["success"] == 2
    finally:
        settings.model_dir = old_model_dir
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_refresh_universe_background_uses_queue_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.jobs as jobs_api
    from main import app

    class _FakeQueue:
        def __init__(self) -> None:
            self.items: list[tuple[str, dict]] = []

        def enqueue(self, run_id: str, payload: dict) -> None:
            self.items.append((run_id, payload))

    fake = _FakeQueue()
    old_backend = settings.job_queue_backend
    settings.job_queue_backend = "postgres"
    monkeypatch.setattr(jobs_api, "get_job_queue", lambda: fake)
    monkeypatch.setattr(jobs_api, "safe_queue_status", lambda _: "queued")
    app.dependency_overrides[get_batch_refresh_orchestrator] = lambda: BatchRefreshOrchestrator(
        market=_FakeMarket(),
        fundamentals=_FakeFundamentals(),
        etl_runner=_FakeETL(),
        retry_attempts=1,
        retry_wait_sec=0.01,
    )
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/jobs/refresh-universe",
            json={"tickers": ["AAPL"], "background": True, "run_etl": False},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["status"] == "queued"
        assert len(fake.items) == 1
        run_id, queued_payload = fake.items[0]
        assert run_id == payload["run_id"]
        assert queued_payload["tickers"] == ["AAPL"]
    finally:
        settings.job_queue_backend = old_backend
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_worker_health_endpoint_uses_queue_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.jobs as jobs_api
    from main import app

    monkeypatch.setattr(
        jobs_api,
        "safe_queue_snapshot",
        lambda *, stale_after_sec: {
            "queued": 1,
            "running": 2,
            "completed": 3,
            "failed": 0,
            "stale_running": 0,
            "dead_letter": 0,
        },
    )
    client = TestClient(app)
    r = client.get("/api/v1/jobs/worker/health")
    assert r.status_code == 200
    payload = r.json()
    assert payload["healthy"] is True
    assert payload["snapshot"]["running"] == 2
    assert payload["snapshot"]["dead_letter"] == 0


@pytest.mark.integration
def test_worker_dead_letter_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.jobs as jobs_api
    from main import app

    dead_rows = [
        {
            "run_id": "r1",
            "attempt_count": 3,
            "max_attempts": 3,
            "worker_id": "w1",
            "error": "failed: max delivery attempts reached",
            "updated_at": "2026-03-24T00:00:00Z",
        }
    ]
    monkeypatch.setattr(jobs_api, "safe_dead_letter_list", lambda *, limit=100: dead_rows[:limit])
    monkeypatch.setattr(jobs_api, "safe_requeue_failed", lambda run_id: run_id == "r1")

    client = TestClient(app)
    r = client.get("/api/v1/jobs/worker/dead-letter")
    assert r.status_code == 200
    payload = r.json()
    assert payload["count"] == 1
    assert payload["rows"][0]["run_id"] == "r1"

    ok = client.post("/api/v1/jobs/worker/dead-letter/r1/requeue")
    assert ok.status_code == 200
    assert ok.json()["status"] == "queued"

    nf = client.post("/api/v1/jobs/worker/dead-letter/unknown/requeue")
    assert nf.status_code == 404
