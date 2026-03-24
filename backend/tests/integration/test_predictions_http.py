"""HTTP-level checks (dependency overrides, no real models on disk)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions import FeatureDataMissingError
from app.domain.identifiers import ModelId
from app.domain.prediction import PredictionReadinessOutcome
from app.services.dependencies import (
    get_batch_refresh_orchestrator,
    get_job_store,
    get_prediction_service,
)


@pytest.mark.integration
def test_get_prediction_503_when_features_missing() -> None:
    from main import app

    class _Svc:
        async def predict(self, ticker: str, model_id: ModelId):
            raise FeatureDataMissingError("processed features not found")

    app.dependency_overrides[get_prediction_service] = lambda: _Svc()
    try:
        client = TestClient(app)
        r = client.get("/api/v1/predictions/TEST?model=model_a")
        assert r.status_code == 503
        body = r.json()
        assert (
            "processed" in body["error"]["message"].lower()
            or "feature" in body["error"]["message"].lower()
        )
        assert "request_id" in body["error"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_get_prediction_readiness_200() -> None:
    from main import app

    class _Svc:
        async def readiness(self, ticker: str, model_id: ModelId):
            _ = model_id
            return PredictionReadinessOutcome(
                ticker=ticker.upper(),
                model_id="model_d",
                ready=False,
                checks={
                    "model_artifact": {"ok": False, "detail": "missing model file"},
                    "combined_features": {"ok": False, "detail": "missing columns"},
                },
            )

    app.dependency_overrides[get_prediction_service] = lambda: _Svc()
    try:
        client = TestClient(app)
        r = client.get("/api/v1/predictions/AAPL/readiness?model=model_d")
        assert r.status_code == 200
        payload = r.json()
        assert payload["ticker"] == "AAPL"
        assert payload["ready"] is False
        assert payload["checks"]["model_artifact"]["ok"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_post_prediction_ensure_ready_runs_refresh_and_returns_delta() -> None:
    from main import app

    class _Svc:
        def __init__(self) -> None:
            self._n = 0

        async def readiness(self, ticker: str, model_id: ModelId):
            _ = model_id
            self._n += 1
            if self._n == 1:
                return PredictionReadinessOutcome(
                    ticker=ticker.upper(),
                    model_id="model_d",
                    ready=False,
                    checks={"combined_features": {"ok": False, "detail": "missing"}},
                )
            return PredictionReadinessOutcome(
                ticker=ticker.upper(),
                model_id="model_d",
                ready=True,
                checks={"combined_features": {"ok": True, "detail": "rows=123"}},
            )

    class _Orchestrator:
        async def run(
            self,
            tickers,
            *,
            run_id=None,
            force_full=False,
            refresh_quote=True,
            refresh_fundamentals=True,
            run_etl=False,
        ):
            _ = (
                tickers,
                run_id,
                force_full,
                refresh_quote,
                refresh_fundamentals,
                run_etl,
            )
            from pathlib import Path

            return Path("/tmp/status.json"), Path("/tmp/lineage.jsonl")

    app.dependency_overrides[get_prediction_service] = lambda: _Svc()
    app.dependency_overrides[get_batch_refresh_orchestrator] = lambda: _Orchestrator()
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/predictions/AAPL/ensure-ready?model=model_d",
            json={"run_etl": True},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["ticker"] == "AAPL"
        assert payload["before_ready"] is False
        assert payload["after_ready"] is True
        assert payload["changed"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_get_prediction_status_includes_recommended_action_and_latest_job() -> None:
    from main import app

    class _Svc:
        async def readiness(self, ticker: str, model_id: ModelId):
            _ = model_id
            return PredictionReadinessOutcome(
                ticker=ticker.upper(),
                model_id="model_d",
                ready=False,
                checks={
                    "raw_ohlcv": {"ok": False, "detail": "/tmp/missing_ohlcv.parquet"},
                    "processed_technical": {"ok": False, "detail": "/tmp/missing_tech.parquet"},
                    "model_artifact": {"ok": True, "detail": "/tmp/model.joblib"},
                },
            )

    class _Store:
        def latest_lineage_for_ticker(self, ticker: str):
            return {"ticker": ticker.upper(), "status": "ok", "etl_status": "ok"}

    app.dependency_overrides[get_prediction_service] = lambda: _Svc()
    app.dependency_overrides[get_job_store] = lambda: _Store()
    try:
        client = TestClient(app)
        r = client.get("/api/v1/predictions/AAPL/status?model=model_d")
        assert r.status_code == 200
        payload = r.json()
        assert payload["ready"] is False
        assert payload["recommended_action"] == "run_ensure_ready_with_etl"
        assert payload["latest_job"]["ticker"] == "AAPL"
        assert payload["freshness"]["raw_ohlcv"]["exists"] is False
    finally:
        app.dependency_overrides.clear()
