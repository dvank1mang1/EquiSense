"""Time-series aware splits for panel data (date + ticker rows)."""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np
import pandas as pd


def walk_forward_expanding_splits(
    dates: np.ndarray,
    *,
    n_splits: int = 4,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Expanding window: fold k uses train on dates [0, train_end_k) and test on [train_end_k, test_end_k).

    Timeline is split into (n_splits + 1) contiguous segments; train grows each fold.
    """
    u = np.sort(np.unique(dates))
    n = len(u)
    if n_splits < 1:
        raise ValueError("n_splits must be >= 1")
    n_blocks = n_splits + 1
    out: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(1, n_splits + 1):
        train_end = int(k / n_blocks * n)
        test_end = int((k + 1) / n_blocks * n)
        train_d = u[:train_end]
        test_d = u[train_end:test_end]
        if len(train_d) < 20 or len(test_d) < 3:
            continue
        out.append((train_d, test_d))
    return out


def purged_kfold_splits(
    dates: np.ndarray,
    *,
    n_splits: int = 5,
    embargo_days: int = 5,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Non-overlapping test blocks on the timeline; train is strictly before each test block.

    Drops `embargo_days` indices from the end of the train set relative to test start
    (simple embargo to reduce label/feature overlap near the boundary).
    """
    u = np.sort(np.unique(dates))
    n = len(u)
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    fold_size = max(1, n // n_splits)
    out: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(n_splits):
        test_start = k * fold_size
        test_end = (k + 1) * fold_size if k < n_splits - 1 else n
        test_d = u[test_start:test_end]
        train_end_idx = test_start - embargo_days
        if train_end_idx <= 0:
            continue
        train_d = u[:train_end_idx]
        if len(train_d) < 20 or len(test_d) < 3:
            continue
        out.append((train_d, test_d))
    return out


def purged_kfold_with_horizon(
    dates: np.ndarray,
    *,
    n_splits: int = 5,
    label_horizon_days: int = 1,
    embargo_days: int = 5,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Purged k-fold with explicit label horizon.

    Train uses only dates strictly before:
      test_start - label_horizon_days - embargo_days

    This is stricter than simple embargo and reduces leakage when targets depend on t+H.
    """
    u = np.sort(np.unique(dates))
    n = len(u)
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    if label_horizon_days < 1:
        raise ValueError("label_horizon_days must be >= 1")
    fold_size = max(1, n // n_splits)
    out: list[tuple[np.ndarray, np.ndarray]] = []
    for k in range(n_splits):
        test_start = k * fold_size
        test_end = (k + 1) * fold_size if k < n_splits - 1 else n
        test_d = u[test_start:test_end]
        train_end_idx = test_start - label_horizon_days - embargo_days
        if train_end_idx <= 0:
            continue
        train_d = u[:train_end_idx]
        if len(train_d) < 20 or len(test_d) < 3:
            continue
        out.append((train_d, test_d))
    return out


def mask_for_dates(df_dates: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    """Boolean mask: row i included iff df_dates[i] is in allowed set."""
    d = pd.to_datetime(pd.Series(np.asarray(df_dates)), utc=False).dt.normalize()
    a = pd.to_datetime(pd.Series(np.asarray(allowed)), utc=False).dt.normalize()
    return d.isin(a).to_numpy(dtype=bool)


def _block_index_ranges(n: int, n_groups: int) -> list[tuple[int, int]]:
    edges = np.linspace(0, n, n_groups + 1, dtype=int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(n_groups)]


def _purge_train_by_label_overlap(
    train_pos: set[int],
    test_pos: set[int],
    *,
    label_horizon_days: int,
    embargo_days: int,
    n_dates: int,
) -> set[int]:
    """
    AFML-style purge: drop train calendar indices i where the label window [i, i+H]
    overlaps the test span expanded by embargo (pre/post test leakage bands).

    For a daily row at date index i with forward horizon H, the realized label depends
    on information through i+H (inclusive on the unique-date index line).
    """
    if label_horizon_days < 1:
        raise ValueError("label_horizon_days must be >= 1")
    if not test_pos:
        return train_pos
    t_lo = min(test_pos)
    t_hi = max(test_pos)
    forb_lo = max(0, t_lo - embargo_days)
    forb_hi = min(n_dates - 1, t_hi + embargo_days)
    h = int(label_horizon_days)
    out: set[int] = set()
    for i in train_pos:
        i_hi = min(i + h, n_dates - 1)
        if i <= forb_hi and i_hi >= forb_lo:
            continue
        out.add(i)
    return out


def combinatorial_purged_cv_splits(
    dates: np.ndarray,
    *,
    n_groups: int = 8,
    test_n_groups: int = 2,
    embargo_days: int = 5,
    label_horizon_days: int = 1,
    max_splits: int = 24,
    seed: int = 42,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Combinatorial Purged CV (CPCV) — перебор комбинаций тестовых блоков на временной оси.

    Таймлайн делится на `n_groups` последовательных блоков; тест = объединение `test_n_groups` блоков.
    Train = дополнение теста, из которого выкинуты даты, чьё окно метки [i, i+H] пересекается
    с расширенным тестовым интервалом (embargo до/после теста), см. `_purge_train_by_label_overlap`.
    Если комбинаций слишком много, случайно сэмплируем до `max_splits`.
    """
    u = np.sort(np.unique(dates))
    n = len(u)
    if n_groups < 3:
        raise ValueError("n_groups must be >= 3")
    if test_n_groups < 1 or test_n_groups >= n_groups:
        raise ValueError("test_n_groups must be in [1, n_groups-1]")
    ranges = _block_index_ranges(n, n_groups)
    combs: Sequence[tuple[int, ...]] = list(itertools.combinations(range(n_groups), test_n_groups))
    if len(combs) > max_splits:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(combs), size=max_splits, replace=False)
        combs = [combs[i] for i in idx]

    out: list[tuple[np.ndarray, np.ndarray]] = []
    for comb in combs:
        test_pos: set[int] = set()
        for g in comb:
            a, b = ranges[g]
            test_pos.update(range(a, b))
        test_d = u[sorted(test_pos)]
        all_pos = set(range(n))
        train_pos = all_pos - test_pos
        train_kept = _purge_train_by_label_overlap(
            train_pos,
            test_pos,
            label_horizon_days=label_horizon_days,
            embargo_days=embargo_days,
            n_dates=n,
        )
        if len(train_kept) < 30 or len(test_d) < 5:
            continue
        train_d = u[sorted(train_kept)]
        out.append((train_d, test_d))
    return out
