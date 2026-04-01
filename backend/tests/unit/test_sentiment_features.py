"""SentimentFeatureEngineer — empty path avoids loading FinBERT."""

from __future__ import annotations

import pandas as pd
import pytest

from app.features.sentiment import SentimentFeatureEngineer


@pytest.mark.unit
def test_compute_empty_news_returns_zeros_aligned_to_dates() -> None:
    eng = SentimentFeatureEngineer()
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    out = eng.compute([], dates, window=3)
    assert len(out) == 3
    assert list(out.columns) == [
        "date",
        "sentiment_score",
        "news_count",
        "positive_ratio",
        "negative_ratio",
        "sentiment_std",
    ]
    assert (out["news_count"] == 0).all()
    assert (out["sentiment_score"] == 0.0).all()
