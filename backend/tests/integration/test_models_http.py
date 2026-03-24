from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_train_model_lifecycle_http() -> None:
    from main import app

    client = TestClient(app)
    r = client.post("/api/v1/models/model_d/train", json={"ticker": "AAPL"})
    assert r.status_code == 200
    run = r.json()
    assert run["model_id"] == "model_d"
    assert run["ticker"] == "AAPL"
    run_id = run["run_id"]

    # Poll briefly; training check is lightweight and should complete quickly.
    status = None
    for _ in range(10):
        rs = client.get(f"/api/v1/models/model_d/train/{run_id}")
        assert rs.status_code == 200
        status = rs.json()["status"]
        if status in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert status in {"completed", "failed"}
