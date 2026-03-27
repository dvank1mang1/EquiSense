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
    get_training_service,
)


@pytest.mark.integration
def test_get_prediction_503_when_features_missing() -> None:
    from main import app

    class _Svc:
        async def predict(
            self, ticker: str, model_id: ModelId, *, artifact_path: str | None = None
        ):
            _ = artifact_path
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
        async def readiness(
            self, ticker: str, model_id: ModelId, *, artifact_path: str | None = None
        ):
            _ = model_id
            _ = artifact_path
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

        async def readiness(
            self, ticker: str, model_id: ModelId, *, artifact_path: str | None = None
        ):
            _ = model_id
            _ = artifact_path
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
        async def readiness(
            self, ticker: str, model_id: ModelId, *, artifact_path: str | None = None
        ):
            _ = model_id
            _ = artifact_path
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


@pytest.mark.integration
def test_get_prediction_accepts_champion_selector() -> None:
    from main import app

    class _Svc:
        async def predict(
            self, ticker: str, model_id: ModelId, *, artifact_path: str | None = None
        ):
            from app.domain.prediction import PredictionOutcome

            assert model_id == ModelId.MODEL_D
            assert artifact_path == "/tmp/champion-model.joblib"
            return PredictionOutcome(
                ticker=ticker.upper(),
                model_id=model_id.value,
                probability=0.6,
                signal="Buy",
                confidence=0.2,
                explanation={"stage": "test"},
            )

    class _Training:
        class _State:
            champion_run_id = "run-123"

        class _Run:
            artifact_path = "/tmp/champion-model.joblib"

        async def get_lifecycle(self, model_id: str):
            _ = model_id
            return self._State()

        async def get_status(self, run_id: str):
            _ = run_id
            return self._Run()

    app.dependency_overrides[get_prediction_service] = lambda: _Svc()
    app.dependency_overrides[get_training_service] = lambda: _Training()
    try:
        client = TestClient(app)
        r = client.get("/api/v1/predictions/AAPL?model=champion")
        assert r.status_code == 200
        payload = r.json()
        assert payload["model"] == "model_d"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_get_prediction_compare_returns_mixed_model_results() -> None:
    from main import app

    class _Svc:
        async def predict(
            self, ticker: str, model_id: ModelId, *, artifact_path: str | None = None
        ):
            from app.domain.prediction import PredictionOutcome

            _ = artifact_path
            if model_id == ModelId.MODEL_C:
                raise FeatureDataMissingError("missing combined features")
            p_map = {
                ModelId.MODEL_A: 0.55,
                ModelId.MODEL_B: 0.62,
                ModelId.MODEL_D: 0.48,
            }
            signal_map = {
                ModelId.MODEL_A: "Buy",
                ModelId.MODEL_B: "Strong Buy",
                ModelId.MODEL_D: "Hold",
            }
            return PredictionOutcome(
                ticker=ticker.upper(),
                model_id=model_id.value,
                probability=p_map[model_id],
                signal=signal_map[model_id],
                confidence=abs(p_map[model_id] - 0.5) * 2.0,
                explanation={"stage": "test"},
            )

    app.dependency_overrides[get_prediction_service] = lambda: _Svc()
    try:
        client = TestClient(app)
        r = client.get("/api/v1/predictions/AAPL/compare")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "AAPL"
        assert body["comparison"]["model_a"]["ok"] is True
        assert body["comparison"]["model_a"]["signal"] == "Buy"
        assert body["comparison"]["model_b"]["probability"] == pytest.approx(0.62, rel=1e-6)
        assert body["comparison"]["model_c"]["ok"] is False
        assert "missing" in body["comparison"]["model_c"]["error"].lower()
        assert body["comparison"]["model_d"]["signal"] == "Hold"
    finally:
        app.dependency_overrides.clear()
