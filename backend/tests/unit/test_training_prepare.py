"""Sanity checks for training frame construction (target = next-day return sign)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.training_service import _prepare_training_frames


def _minimal_feats() -> list[str]:
    return ["returns", "rsi", "volatility"]


def test_target_matches_next_calendar_returns() -> None:
    dates = pd.date_range("2020-01-02", periods=90, freq="D")
    rng = np.random.default_rng(2)
    df = pd.DataFrame(
        {
            "date": dates,
            "returns": rng.standard_normal(90) * 0.02,
            "rsi": 50.0,
            "volatility": 0.02,
        }
    )
    df2 = df.sort_values("date").reset_index(drop=True)
    next_ret = pd.to_numeric(df2["returns"], errors="coerce").shift(-1)
    valid = next_ret.notna()
    ref = pd.DataFrame(
        {
            "date": df2.loc[valid, "date"].values,
            "expected": (next_ret[valid] > 0.0).astype("int64").values,
        }
    )
    train, val, test = _prepare_training_frames(df, _minimal_feats())
    out = pd.concat([train, val, test], ignore_index=True)
    merged = out.merge(ref, on="date", how="inner")
    assert len(merged) == len(out)
    assert (merged["target"] == merged["expected"]).all()


def test_deduplicates_duplicate_dates() -> None:
    dates = pd.date_range("2021-06-01", periods=70, freq="D")
    dup = list(dates) + [dates[10]]
    rng = np.random.default_rng(3)
    df = pd.DataFrame(
        {
            "date": dup,
            "returns": rng.standard_normal(71) * 0.01,
            "rsi": rng.uniform(20, 80, 71),
            "volatility": 0.02,
        }
    )
    train, val, test = _prepare_training_frames(df, _minimal_feats())
    all_dates = pd.concat([train, val, test])["date"]
    assert not all_dates.duplicated().any()


def test_time_split_train_before_test() -> None:
    dates = pd.date_range("2018-01-01", periods=100, freq="B")
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "date": dates,
            "returns": rng.standard_normal(100) * 0.01,
            "rsi": rng.uniform(30, 70, 100),
            "volatility": rng.uniform(0.01, 0.05, 100),
        }
    )
    train, val, test = _prepare_training_frames(df, _minimal_feats())
    assert pd.to_datetime(train["date"]).max() < pd.to_datetime(val["date"]).min()
    assert pd.to_datetime(val["date"]).max() < pd.to_datetime(test["date"]).min()


def test_too_few_rows_raises() -> None:
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    df = pd.DataFrame(
        {
            "date": dates,
            "returns": np.linspace(-0.01, 0.01, 10),
            "rsi": 50.0,
            "volatility": 0.02,
        }
    )
    with pytest.raises(ValueError, match="at least 60 rows"):
        _prepare_training_frames(df, _minimal_feats())
