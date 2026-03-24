from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_train_model_lifecycle_http() -> None:
    from main import app

    # Must use context manager: one shared anyio portal + lifespan. Without it, each
    # request spins a new portal and closes it — asyncio.create_task training jobs
    # are cancelled and status stays "running" forever (flaky / always fails on CI).
    with TestClient(app) as client:
        r = client.post("/api/v1/models/model_d/train", json={"ticker": "AAPL"})
        assert r.status_code == 200
        run = r.json()
        assert run["model_id"] == "model_d"
        assert run["ticker"] == "AAPL"
        run_id = run["run_id"]

        # Poll until terminal state (CI runners can be slow; XGBoost fit is not instant).
        status = None
        payload: dict[str, Any] = {}
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            rs = client.get(f"/api/v1/models/model_d/train/{run_id}")
            assert rs.status_code == 200
            payload = rs.json()
            status = payload["status"]
            if status in {"completed", "failed"}:
                break
            time.sleep(0.1)
        assert status in {"completed", "failed"}, (
            f"training still {status!r} after 60s — pipeline hung or TestClient misuse"
        )
        assert payload["params"]["target"] == "next_day_return_gt_0"
        if status == "completed":
            assert isinstance(payload["dataset_fingerprint"], str)
            assert len(payload["dataset_fingerprint"]) == 16
            assert "f1" in payload["metrics"]

        rl = client.get("/api/v1/models/model_d/experiments", params={"limit": 5})
        assert rl.status_code == 200
        listed = rl.json()
        assert listed["total"] >= 1
        assert any(item["run_id"] == run_id for item in listed["items"])

        one = client.get(f"/api/v1/models/model_d/experiments/{run_id}")
        assert one.status_code == 200
        assert one.json()["run_id"] == run_id

        lifecycle_before = client.get("/api/v1/models/model_d/lifecycle")
        assert lifecycle_before.status_code == 200
        assert lifecycle_before.json()["champion_run_id"] in {None, run_id}

        if status == "completed":
            promote = client.post(
                f"/api/v1/models/model_d/lifecycle/promote/{run_id}",
                json={"reason": "best holdout metrics"},
            )
            assert promote.status_code == 200
            promoted = promote.json()
            assert promoted["champion_run_id"] == run_id
            assert len(promoted["history"]) >= 1

        champions = client.get("/api/v1/models/lifecycle/champions")
        assert champions.status_code == 200
        data = champions.json()
        assert data["total"] >= 4
        assert any(item["model_id"] == "model_d" for item in data["items"])
