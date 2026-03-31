"""Discovery endpoint for /api/v1/."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_api_v1_root_lists_routers() -> None:
    from main import app

    with TestClient(app) as client:
        r = client.get("/api/v1/")
        assert r.status_code == 200
        body = r.json()
        assert body["api_version"] == "v1"
        assert isinstance(body.get("release"), str) and body["release"]
        assert "docs" in body
        assert body["health"] == "/health"
        assert "/api/v1/models" in body["routers"].values()
