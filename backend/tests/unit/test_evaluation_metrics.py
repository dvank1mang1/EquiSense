"""Sanity checks for cross-sectional IC / financial selection helpers."""

import numpy as np
import pandas as pd

from app.ml.evaluation import financial_selection_metrics, information_coefficient_metrics


def test_information_coefficient_negated_score_is_opposite_sign() -> None:
    rng = np.random.default_rng(0)
    dates = np.repeat(pd.date_range("2020-01-01", periods=20, freq="D"), 15)
    n = len(dates)
    score = rng.normal(size=n)
    ret = 0.5 * score + rng.normal(scale=0.5, size=n)
    frame = pd.DataFrame({"date": dates, "score": score, "forward_return": ret})
    m = information_coefficient_metrics(frame, include_negated_score=True)
    assert np.isfinite(m["ic_mean"])
    assert np.isfinite(m["ic_mean_neg_score"])
    assert abs(m["ic_mean"] + m["ic_mean_neg_score"]) < 0.02
    assert np.isfinite(m["rank_ic_mean"])
    assert np.isfinite(m["rank_ic_mean_neg_score"])
    assert abs(m["rank_ic_mean"] + m["rank_ic_mean_neg_score"]) < 0.02


def test_financial_selection_label_threshold_hit_rate() -> None:
    # One date: top 50% by score → two names; one return > 0, one not; both > 1% threshold? only first.
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01"] * 4),
            "score": [4.0, 3.0, 2.0, 1.0],
            "forward_return": [0.02, 0.005, -0.02, -0.01],
        }
    )
    m0 = financial_selection_metrics(frame, top_q=0.5, label_return_threshold=None)
    assert "hit_rate_top_quantile_above_threshold" not in m0
    m1 = financial_selection_metrics(frame, top_q=0.5, label_return_threshold=0.01)
    assert m1["hit_rate_top_quantile_above_threshold"] == 0.5
    assert m1["hit_rate_top_quantile"] == 1.0


def test_financial_selection_empty() -> None:
    assert financial_selection_metrics(pd.DataFrame()) == {}
