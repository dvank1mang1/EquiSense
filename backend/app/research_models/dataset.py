from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.contracts.features import FeatureStorePort
from app.features.constants import FUNDAMENTAL_FEATURES, SENTIMENT_FEATURES, TECHNICAL_FEATURES

FEATURE_COLUMNS: list[str] = TECHNICAL_FEATURES + FUNDAMENTAL_FEATURES + SENTIMENT_FEATURES


@dataclass
class ResearchDataset:
    panel: pd.DataFrame
    feature_columns: list[str]


def _compute_forward_5d_from_returns(ret: pd.Series) -> pd.Series:
    out = pd.Series(index=ret.index, dtype=float)
    for i in range(len(ret)):
        window = ret.iloc[i + 1 : i + 6]
        if len(window) < 5 or window.isna().any():
            out.iloc[i] = np.nan
        else:
            out.iloc[i] = float(np.prod(1.0 + window.values) - 1.0)
    return out


def _enrich_targets_and_regimes(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["returns"] = pd.to_numeric(work["returns"], errors="coerce")
    work["fwd_1d"] = work["returns"].shift(-1)
    work["fwd_5d"] = _compute_forward_5d_from_returns(work["returns"])
    work["target_cls"] = (work["fwd_5d"] > 0.0).astype("int64")
    vol20 = work["returns"].rolling(20, min_periods=10).std()
    vol_med = vol20.expanding(min_periods=20).median()
    work["regime_high_vol"] = (vol20 > vol_med).astype("int64")

    s20 = pd.to_numeric(work.get("sma_20"), errors="coerce")
    s50 = pd.to_numeric(work.get("sma_50"), errors="coerce")
    work["regime_trend"] = (s20 > s50).astype("int64")
    return work


def build_research_panel(store: FeatureStorePort, tickers: list[str]) -> ResearchDataset:
    rows: list[pd.DataFrame] = []
    for t in tickers:
        ticker = t.strip().upper()
        if not ticker:
            continue
        base = store.build_combined(ticker).copy()
        if base.empty or "date" not in base.columns or "returns" not in base.columns:
            continue
        base["date"] = pd.to_datetime(base["date"], errors="coerce")
        base = (
            base.dropna(subset=["date"])
            .sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
        )
        base["ticker"] = ticker
        base = _enrich_targets_and_regimes(base)
        rows.append(base)

    if not rows:
        raise ValueError("research panel is empty: no valid features for requested tickers")

    panel = pd.concat(rows, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
    panel = panel.dropna(subset=["date"])
    panel = panel.sort_values(["date", "ticker"]).reset_index(drop=True)

    # Keep rows with known target and at least one usable feature.
    feat_block = panel.reindex(columns=FEATURE_COLUMNS)
    panel = panel.loc[~feat_block.isna().all(axis=1)].copy()
    panel = panel.dropna(subset=["fwd_5d", "fwd_1d"])
    if panel.empty:
        raise ValueError("research panel is empty after target construction")

    return ResearchDataset(panel=panel, feature_columns=list(FEATURE_COLUMNS))


def split_panel_by_date(
    panel: pd.DataFrame,
    *,
    train_fraction: float = 0.7,
    val_end_fraction: float = 0.85,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not (0.0 < train_fraction < val_end_fraction < 1.0):
        raise ValueError("need 0 < train_fraction < val_end_fraction < 1")
    dates = np.sort(panel["date"].dt.normalize().unique())
    if len(dates) < 40:
        raise ValueError("not enough unique dates for research split (need >= 40)")
    i_val = max(10, min(int(len(dates) * train_fraction), len(dates) - 20))
    i_test = max(i_val + 5, min(int(len(dates) * val_end_fraction), len(dates) - 5))
    train_dates = set(dates[:i_val])
    val_dates = set(dates[i_val:i_test])
    test_dates = set(dates[i_test:])
    train_df = panel[panel["date"].dt.normalize().isin(train_dates)].copy()
    val_df = panel[panel["date"].dt.normalize().isin(val_dates)].copy()
    test_df = panel[panel["date"].dt.normalize().isin(test_dates)].copy()
    if train_df.empty or val_df.empty or test_df.empty:
        raise ValueError("empty train/val/test split in research panel")
    return train_df, val_df, test_df
