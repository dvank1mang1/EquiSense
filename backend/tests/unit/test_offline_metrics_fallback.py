"""offline_metrics_for_ticker_model: same-ticker vs flat-file fallback."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.domain.identifiers import ModelId
from app.services.experiment_store import InMemoryExperimentStore
from app.services.lifecycle_store import InMemoryLifecycleStore
from app.services.training_service import TrainingRegistry, TrainingRun, TrainingService


@pytest.mark.asyncio
async def test_offline_metrics_same_ticker_from_flat_file(tmp_path: Path) -> None:
    model_root = tmp_path / "mdl"
    model_root.mkdir()
    sym = "JPM"
    payload = {"ticker": sym, "f1": 0.5, "roc_auc": 0.55, "ic_mean": 0.01}
    (model_root / "model_a.metrics.json").write_text(json.dumps(payload), encoding="utf-8")

    class _Cfg:
        model_dir = str(model_root)

    svc = TrainingService(
        features=MagicMock(),
        registry=TrainingRegistry(),
        experiment_store=InMemoryExperimentStore(),
        lifecycle=InMemoryLifecycleStore(),
    )
    with patch("app.services.training_service.get_settings", return_value=_Cfg()):
        res = await svc.offline_metrics_for_ticker_model(ModelId.MODEL_A, sym)
    assert res.source == "same_ticker_holdout"
    assert res.trained_ticker == sym
    assert res.metrics.get("f1") == pytest.approx(0.5)
    assert res.metrics.get("ic_mean") == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_offline_metrics_fallback_other_ticker_flat_file(tmp_path: Path) -> None:
    model_root = tmp_path / "mdl"
    model_root.mkdir()
    payload = {"ticker": "MSFT", "f1": 0.42, "roc_auc": 0.58}
    (model_root / "model_a.metrics.json").write_text(json.dumps(payload), encoding="utf-8")

    class _Cfg:
        model_dir = str(model_root)

    svc = TrainingService(
        features=MagicMock(),
        registry=TrainingRegistry(),
        experiment_store=InMemoryExperimentStore(),
        lifecycle=InMemoryLifecycleStore(),
    )
    with patch("app.services.training_service.get_settings", return_value=_Cfg()):
        res = await svc.offline_metrics_for_ticker_model(ModelId.MODEL_A, "AAPL")
    assert res.source == "other_ticker_flat_file"
    assert res.trained_ticker == "MSFT"
    assert res.metrics.get("f1") == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_offline_metrics_champion_other_ticker_before_flat(tmp_path: Path) -> None:
    """Champion run (different ticker) wins over flat file fallback order."""
    model_root = tmp_path / "mdl"
    model_root.mkdir()
    (model_root / "model_a.metrics.json").write_text(
        json.dumps({"ticker": "XOM", "f1": 0.1, "roc_auc": 0.2}),
        encoding="utf-8",
    )

    class _Cfg:
        model_dir = str(model_root)

    reg = TrainingRegistry()
    store = InMemoryExperimentStore()
    life = InMemoryLifecycleStore()
    run = TrainingRun(
        run_id="run-champ-1",
        model_id=ModelId.MODEL_A.value,
        ticker="NVDA",
        status="completed",
        created_at="2020-01-01T00:00:00+00:00",
        updated_at="2020-01-01T00:00:00+00:00",
        metrics={"f1": 0.77, "roc_auc": 0.88},
    )
    await store.upsert(run)
    await life.promote(ModelId.MODEL_A.value, run.run_id, reason="test")

    svc = TrainingService(
        features=MagicMock(),
        registry=reg,
        experiment_store=store,
        lifecycle=life,
    )
    with patch("app.services.training_service.get_settings", return_value=_Cfg()):
        res = await svc.offline_metrics_for_ticker_model(ModelId.MODEL_A, "AAPL")
    assert res.source == "other_ticker_champion"
    assert res.trained_ticker == "NVDA"
    assert res.metrics.get("f1") == pytest.approx(0.77)
