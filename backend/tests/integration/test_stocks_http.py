"""HTTP checks for stocks router."""

from __future__ import annotations

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
