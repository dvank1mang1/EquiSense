"""Fundamental features — aligned with model_b FUNDAMENTAL_FEATURES."""

import pytest

from app.features.constants import FUNDAMENTAL_FEATURES
from app.features.fundamental import FundamentalFeatureEngineer, enrich_overview_for_ui


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

    def test_compute_dividend_yield_ratio_and_percent(self) -> None:
        eng = FundamentalFeatureEngineer()
        assert eng.compute({"Symbol": "X", "DividendYield": "0.02"})["dividend_yield"] == 0.02
        assert eng.compute({"Symbol": "X", "DividendYield": "2.5"})["dividend_yield"] == 0.025

    def test_enrich_merges_ui_metrics(self, sample_overview_dict: dict) -> None:
        merged = enrich_overview_for_ui(sample_overview_dict)
        assert merged["PERatio"] == "28.5"
        assert merged["pe_ratio"] == 28.5
        assert merged["dividend_yield"] == 0.015

    def test_enrich_calls_yfinance_when_cache_thin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.data.yfinance_overview as yfo

        def fake_patch(sym: str) -> dict:
            assert sym == "ZZZ"
            return {
                "PERatio": "19",
                "EPS": "2.5",
                "QuarterlyRevenueGrowthYOY": "0.1",
                "ReturnOnEquityTTM": "0.12",
                "DebtToEquityRatio": "0.4",
                "DividendYield": "0.01",
            }

        monkeypatch.setattr(yfo, "yfinance_av_overview_patch", fake_patch)
        thin = {"Symbol": "ZZZ", "Name": "ZZZ Inc"}
        merged = enrich_overview_for_ui(thin)
        assert merged["pe_ratio"] == 19.0
        assert merged["eps"] == 2.5
        assert merged["revenue_growth"] == pytest.approx(0.1)
        assert merged["roe"] == pytest.approx(0.12)
        assert merged["debt_to_equity"] == pytest.approx(0.4)
        assert merged["dividend_yield"] == pytest.approx(0.01)
