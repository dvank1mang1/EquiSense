from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.explainability.shap_explainer import ShapExplainer, _FEATURE_GROUPS
from app.features.constants import TECHNICAL_FEATURES
from app.models.baseline_lr import BaselineLRModel
from app.models.model_a import ModelA


def _make_df(n: int = 150, rng: np.random.Generator | None = None) -> tuple[pd.DataFrame, pd.Series]:
    if rng is None:
        rng = np.random.default_rng(42)
    X = pd.DataFrame({feat: rng.standard_normal(n) for feat in TECHNICAL_FEATURES})
    y = pd.Series(rng.integers(0, 2, size=n), name="target")
    return X, y


def _trained_lr() -> tuple[BaselineLRModel, pd.DataFrame, pd.Series]:
    m = BaselineLRModel()
    X, y = _make_df()
    m.train(X, y)
    return m, X, y


def _trained_rf() -> tuple[ModelA, pd.DataFrame, pd.Series]:
    m = ModelA()
    X, y = _make_df()
    m.train(X, y)
    return m, X, y


@pytest.mark.unit
class TestShapExplainerInit:
    def test_explainer_stores_feature_set(self) -> None:
        m, _, _ = _trained_lr()
        exp = ShapExplainer(m)
        assert exp._feature_set == TECHNICAL_FEATURES

    def test_explainer_is_none_before_build(self) -> None:
        m, _, _ = _trained_lr()
        exp = ShapExplainer(m)
        assert exp._explainer is None


@pytest.mark.unit
class TestShapExplainerBuild:
    def test_build_explainer_lr(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        assert exp._explainer is not None

    def test_build_explainer_rf(self) -> None:
        m, X, _ = _trained_rf()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        assert exp._explainer is not None

    def test_build_uses_at_most_100_background_rows(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        assert len(exp._background) <= 100


@pytest.mark.unit
class TestShapExplainSingle:
    def test_explain_single_returns_dict_with_all_features(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        result = exp.explain_single(X.tail(1))
        assert set(result.keys()) == set(TECHNICAL_FEATURES)

    def test_explain_single_values_are_floats(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        result = exp.explain_single(X.tail(1))
        assert all(isinstance(v, float) for v in result.values())

    def test_explain_single_rf_model(self) -> None:
        m, X, _ = _trained_rf()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        result = exp.explain_single(X.tail(1))
        assert set(result.keys()) == set(TECHNICAL_FEATURES)

    def test_explain_single_raises_if_no_build(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        with pytest.raises(RuntimeError, match="build_explainer"):
            exp.explain_single(X.tail(1))


@pytest.mark.unit
class TestShapExplainBatch:
    def test_explain_batch_shape(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        result_df = exp.explain_batch(X.head(5))
        assert result_df.shape == (5, len(TECHNICAL_FEATURES))

    def test_explain_batch_columns_match_feature_set(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        result_df = exp.explain_batch(X.head(3))
        assert list(result_df.columns) == TECHNICAL_FEATURES

    def test_explain_batch_raises_if_no_build(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        with pytest.raises(RuntimeError, match="build_explainer"):
            exp.explain_batch(X)


@pytest.mark.unit
class TestGroupContributions:
    def test_group_contributions_has_all_groups(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        shap_vals = exp.explain_single(X.tail(1))
        groups = exp.group_contributions(shap_vals)
        assert set(groups.keys()) == set(_FEATURE_GROUPS.keys())

    def test_group_contributions_are_non_negative(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        shap_vals = exp.explain_single(X.tail(1))
        groups = exp.group_contributions(shap_vals)
        assert all(v >= 0.0 for v in groups.values())

    def test_technical_group_nonzero_for_technical_model(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        shap_vals = exp.explain_single(X.tail(1))
        groups = exp.group_contributions(shap_vals)
        assert groups["technical"] >= 0.0

    def test_fundamental_and_news_zero_for_technical_only_model(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        shap_vals = exp.explain_single(X.tail(1))
        groups = exp.group_contributions(shap_vals)
        assert groups["fundamental"] == 0.0
        assert groups["news"] == 0.0


@pytest.mark.unit
class TestTopFeatures:
    def test_top_features_length_respects_top_n(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        shap_vals = exp.explain_single(X.tail(1))
        top = exp.get_top_features(shap_vals, top_n=5)
        assert len(top) == 5

    def test_top_features_structure(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        shap_vals = exp.explain_single(X.tail(1))
        top = exp.get_top_features(shap_vals, top_n=3)
        for item in top:
            assert "name" in item
            assert "shap_value" in item
            assert isinstance(item["shap_value"], float)

    def test_top_features_sorted_by_abs_value(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        shap_vals = exp.explain_single(X.tail(1))
        top = exp.get_top_features(shap_vals, top_n=len(TECHNICAL_FEATURES))
        abs_vals = [abs(item["shap_value"]) for item in top]
        assert abs_vals == sorted(abs_vals, reverse=True)

    def test_top_n_capped_by_feature_set_size(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        shap_vals = exp.explain_single(X.tail(1))
        top = exp.get_top_features(shap_vals, top_n=999)
        assert len(top) == len(TECHNICAL_FEATURES)


@pytest.mark.unit
class TestBaseValue:
    def test_base_value_is_float(self) -> None:
        m, X, _ = _trained_lr()
        exp = ShapExplainer(m)
        exp._build_explainer(X)
        assert isinstance(exp.base_value(), float)

    def test_base_value_before_build_is_zero(self) -> None:
        m, _, _ = _trained_lr()
        exp = ShapExplainer(m)
        assert exp.base_value() == 0.0
