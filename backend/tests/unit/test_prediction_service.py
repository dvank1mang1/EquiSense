"""PredictionService — inference path (TDD): combined features → predict_proba → signal."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.core.config import settings
from app.domain.exceptions import FeatureDataMissingError, ModelArtifactMissingError
from app.domain.identifiers import ModelId
from app.features.constants import TECHNICAL_FEATURES
from app.services.prediction_service import PredictionService


@pytest.mark.unit
class TestPredictionServiceInference:
    @pytest.mark.asyncio
    async def test_raises_feature_data_missing_when_no_combined_frame(self) -> None:
        market = MagicMock()
        store = MagicMock()
        store.build_combined.side_effect = FeatureDataMissingError("no technical")

        svc = PredictionService(market=market, features=store)

        with patch("app.models.get_model_class") as gmc:

            class _M:
                model_id = "model_a"
                feature_set = TECHNICAL_FEATURES

                def load(self) -> None:
                    pass

                def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
                    raise AssertionError("should not run")

                def get_signal(self, p: float) -> str:
                    return "Hold"

            gmc.return_value = _M

            with pytest.raises(FeatureDataMissingError):
                await svc.predict("X", ModelId.MODEL_A)

    @pytest.mark.asyncio
    async def test_returns_probability_signal_and_confidence_with_mocks(self) -> None:
        market = MagicMock()
        store = MagicMock()
        rows = []
        rng = np.random.default_rng(0)
        for i in range(5):
            row = {"date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)}
            for f in TECHNICAL_FEATURES:
                row[f] = float(rng.normal())
            rows.append(row)
        combined = pd.DataFrame(rows)
        store.build_combined.return_value = combined

        svc = PredictionService(market=market, features=store)

        with patch("app.models.get_model_class") as gmc:

            class _M:
                model_id = "model_a"
                feature_set = TECHNICAL_FEATURES

                def load(self) -> None:
                    pass

                def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
                    assert len(X) == 1
                    return np.array([[0.25, 0.75]])

                def get_signal(self, p: float) -> str:
                    if p >= 0.7:
                        return "Strong Buy"
                    return "Hold"

            gmc.return_value = _M

            out = await svc.predict("  spy  ", ModelId.MODEL_A)

        assert out.ticker == "SPY"
        assert out.model_id == "model_a"
        assert out.probability == pytest.approx(0.75)
        assert out.signal == "Strong Buy"
        assert out.confidence == pytest.approx(0.5)  # |0.75-0.5|*2
        assert out.explanation.get("stage") == "inference_complete"
        store.build_combined.assert_called_once_with("SPY")

    @pytest.mark.asyncio
    async def test_raises_model_artifact_missing_when_load_fails(self) -> None:
        market = MagicMock()
        store = MagicMock()

        svc = PredictionService(market=market, features=store)

        with patch("app.models.get_model_class") as gmc:

            class _M:
                model_id = "model_a"
                feature_set = TECHNICAL_FEATURES

                def load(self) -> None:
                    raise FileNotFoundError("missing.joblib")

            gmc.return_value = _M

            with pytest.raises(ModelArtifactMissingError):
                await svc.predict("AAPL", ModelId.MODEL_A)

        store.build_combined.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_feature_data_missing_when_required_columns_absent(self) -> None:
        market = MagicMock()
        store = MagicMock()
        # only one technical column — not enough for model_a
        store.build_combined.return_value = pd.DataFrame(
            {"date": [pd.Timestamp("2024-01-05")], "rsi": [50.0]}
        )

        svc = PredictionService(market=market, features=store)

        with patch("app.models.get_model_class") as gmc:

            class _M:
                model_id = "model_a"
                feature_set = TECHNICAL_FEATURES

                def load(self) -> None:
                    pass

            gmc.return_value = _M

            with pytest.raises(FeatureDataMissingError, match="Missing feature columns"):
                await svc.predict("AAPL", ModelId.MODEL_A)

    @pytest.mark.asyncio
    async def test_readiness_false_when_model_artifact_missing(self, tmp_path) -> None:
        old_model_dir = settings.model_dir
        settings.model_dir = str(tmp_path / "models")
        try:
            market = MagicMock()
            store = MagicMock()
            store.exists.side_effect = lambda ticker, f: f in ("technical", "fundamental")
            store.path_for.side_effect = lambda ticker, f: (
                tmp_path / "processed" / ticker / f"{f}.parquet"
            )
            store.build_combined.return_value = pd.DataFrame(
                {"date": [pd.Timestamp("2024-01-05")], **{f: [0.1] for f in TECHNICAL_FEATURES}}
            )

            svc = PredictionService(market=market, features=store)

            with patch("app.models.get_model_class") as gmc:

                class _M:
                    model_id = "model_a"
                    feature_set = TECHNICAL_FEATURES

                    def __init__(self) -> None:
                        self.model_path = tmp_path / "models" / "model_a.joblib"

                gmc.return_value = _M
                out = await svc.readiness("AAPL", ModelId.MODEL_A)

            assert out.ticker == "AAPL"
            assert out.ready is False
            assert out.checks["combined_features"]["ok"] is True
            assert out.checks["model_artifact"]["ok"] is False
        finally:
            settings.model_dir = old_model_dir
