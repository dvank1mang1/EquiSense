"""Root /health contract (probes, load balancers)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_health_returns_version_and_api_hints() -> None:
    from main import app

    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "app" in body
        assert isinstance(body.get("version"), str) and body["version"]
        assert body["api"]["prefix"] == "/api/v1"
        assert body["api"]["docs"] == "/docs"
        assert isinstance(body.get("debug"), bool)
