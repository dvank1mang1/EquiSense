"""HTTP-level checks (dependency overrides, no real models on disk)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions import FeatureDataMissingError
from app.domain.identifiers import ModelId
from app.services.dependencies import get_prediction_service


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
        assert "processed" in r.json()["detail"].lower() or "feature" in r.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
