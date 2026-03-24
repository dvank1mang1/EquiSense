"""Fundamental features — aligned with model_b FUNDAMENTAL_FEATURES."""

import pytest

from app.features.constants import FUNDAMENTAL_FEATURES
from app.features.fundamental import FundamentalFeatureEngineer


@pytest.mark.unit
class TestFundamentalFeatureEngineer:
    def test_compute_maps_overview_to_feature_dict(self, sample_overview_dict: dict) -> None:
        out = FundamentalFeatureEngineer().compute(sample_overview_dict)
        for k in FUNDAMENTAL_FEATURES:
            assert k in out

    def test_compute_values_are_floats_or_nan(self, sample_overview_dict: dict) -> None:
        out = FundamentalFeatureEngineer().compute(sample_overview_dict)
        for k in FUNDAMENTAL_FEATURES:
            v = out[k]
            assert v is None or isinstance(v, float)
