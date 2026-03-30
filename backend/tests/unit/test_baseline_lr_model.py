from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from app.domain.identifiers import ModelId
from app.features.constants import TECHNICAL_FEATURES
from app.features.technical import TechnicalFeatureEngineer
from app.models import MODEL_REGISTRY, get_model_class
from app.models.baseline_lr import BaselineLRModel


def _make_feature_df(
    n: int = 120, rng: np.random.Generator | None = None
) -> tuple[pd.DataFrame, pd.Series]:
    if rng is None:
        rng = np.random.default_rng(0)
    X = pd.DataFrame({feat: rng.standard_normal(n) for feat in TECHNICAL_FEATURES})
    y = pd.Series(rng.integers(0, 2, size=n), name="target")
    return X, y


@pytest.mark.unit
class TestBaselineLRIdentity:
    def test_model_id_string(self) -> None:
        assert BaselineLRModel.model_id == "baseline_lr"

    def test_feature_set_equals_technical_features(self) -> None:
        assert BaselineLRModel.feature_set == TECHNICAL_FEATURES

    def test_registered_in_model_registry(self) -> None:
        assert ModelId.BASELINE_LR in MODEL_REGISTRY
        assert MODEL_REGISTRY[ModelId.BASELINE_LR] is BaselineLRModel

    def test_get_model_class_resolves_string(self) -> None:
        cls = get_model_class("baseline_lr")
        assert cls is BaselineLRModel

    def test_model_id_enum_value(self) -> None:
        assert ModelId.BASELINE_LR == "baseline_lr"

    def test_internal_pipeline_is_sklearn_pipeline(self) -> None:
        m = BaselineLRModel()
        assert isinstance(m.model, Pipeline)

    def test_pipeline_has_scaler_and_lr_steps(self) -> None:
        m = BaselineLRModel()
        step_names = [name for name, _ in m.model.steps]
        assert "scaler" in step_names
        assert "lr" in step_names


@pytest.mark.unit
class TestBaselineLRTrainPredict:
    def test_train_sets_is_trained(self) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df()
        m.train(X, y)
        assert m.is_trained is True

    def test_predict_proba_shape(self) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df()
        m.train(X, y)
        proba = m.predict_proba(X)
        assert proba.shape == (len(X), 2)

    def test_predict_proba_values_in_unit_interval(self) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df()
        m.train(X, y)
        proba = m.predict_proba(X)
        assert np.all(proba >= 0.0)
        assert np.all(proba <= 1.0)

    def test_predict_proba_rows_sum_to_one(self) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df()
        m.train(X, y)
        row_sums = m.predict_proba(X).sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

    def test_predict_binary_output(self) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df()
        m.train(X, y)
        preds = m.predict(X)
        assert set(preds).issubset({0, 1})

    def test_uses_only_registered_features(self) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df(n=100)
        m.train(X, y)
        X_extra = X.copy()
        X_extra["unwanted_col"] = 999.0
        proba_base = m.predict_proba(X)
        proba_extra = m.predict_proba(X_extra)
        np.testing.assert_array_equal(proba_base, proba_extra)

    def test_evaluate_returns_required_keys(self) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df(n=200)
        m.train(X, y)
        metrics = m.evaluate(X, y)
        for key in ("f1", "roc_auc", "precision", "recall", "brier", "pr_auc"):
            assert key in metrics
            v = metrics[key]
            assert math.isfinite(v) and 0.0 <= v <= 1.0


@pytest.mark.unit
class TestBaselineLRPersistence:
    def test_save_creates_joblib_file(self, tmp_path: Path) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df()
        m.train(X, y)
        artifact = tmp_path / "baseline_lr_test.joblib"
        m.save(artifact)
        assert artifact.exists()

    def test_load_restores_predictions(self, tmp_path: Path) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df()
        m.train(X, y)
        proba_before = m.predict_proba(X)
        artifact = tmp_path / "baseline_lr_test.joblib"
        m.save(artifact)
        m2 = BaselineLRModel()
        m2.load(artifact)
        proba_after = m2.predict_proba(X)
        np.testing.assert_allclose(proba_before, proba_after, atol=1e-7)

    def test_load_sets_is_trained(self, tmp_path: Path) -> None:
        m = BaselineLRModel()
        X, y = _make_feature_df()
        m.train(X, y)
        artifact = tmp_path / "baseline_lr_test.joblib"
        m.save(artifact)
        m2 = BaselineLRModel()
        assert m2.is_trained is False
        m2.load(artifact)
        assert m2.is_trained is True

    def test_load_missing_artifact_raises(self, tmp_path: Path) -> None:
        m = BaselineLRModel()
        with pytest.raises(FileNotFoundError):
            m.load(tmp_path / "nonexistent.joblib")


@pytest.mark.unit
class TestBaselineLRSignal:
    @pytest.mark.parametrize(
        ("prob", "expected"),
        [
            (0.75, "Strong Buy"),
            (0.60, "Buy"),
            (0.50, "Hold"),
            (0.30, "Sell"),
        ],
    )
    def test_get_signal(self, prob: float, expected: str) -> None:
        assert BaselineLRModel().get_signal(prob) == expected


@pytest.mark.unit
class TestBaselineLRWithRealFeatures:
    def test_train_on_engineered_features(self, sample_ohlcv_df: pd.DataFrame) -> None:
        features_df = TechnicalFeatureEngineer().compute(sample_ohlcv_df)
        features_df = features_df.dropna()
        X = features_df[TECHNICAL_FEATURES].fillna(0.0)
        rng = np.random.default_rng(1)
        y = pd.Series(rng.integers(0, 2, size=len(X)), name="target")
        m = BaselineLRModel()
        m.train(X, y)
        proba = m.predict_proba(X)
        assert proba.shape == (len(X), 2)
        assert np.all(proba >= 0.0) and np.all(proba <= 1.0)
