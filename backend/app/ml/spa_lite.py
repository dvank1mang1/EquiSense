"""SPA-lite: block bootstrap p-value for mean outperformance vs benchmark."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def block_bootstrap_mean_pvalue(
    spread: np.ndarray,
    *,
    n_bootstrap: int = 2000,
    block_len: int = 5,
    seed: int = 42,
) -> dict[str, Any]:
    """
    One-sided p-value for H0: E[spread] <= 0 vs H1: E[spread] > 0.

    Uses circular block bootstrap on the spread series (weak dependence).
    """
    x = np.asarray(spread, dtype=float).ravel()
    x = x[np.isfinite(x)]
    n = len(x)
    if n < block_len * 3:
        return {
            "observed_mean": float(np.mean(x)) if n else float("nan"),
            "p_value_one_sided": 1.0,
            "n_bootstrap": n_bootstrap,
            "block_len": block_len,
            "note": "too_few_observations",
        }

    obs = float(np.mean(x))
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block_len))
    starts = rng.integers(0, n, size=(n_bootstrap, n_blocks))
    counts = np.zeros(n_bootstrap, dtype=float)
    for b in range(n_bootstrap):
        samp_list: list[float] = []
        for j in range(n_blocks):
            s = starts[b, j]
            chunk = [x[(s + k) % n] for k in range(block_len)]
            samp_list.extend(chunk)
        samp = np.array(samp_list[:n], dtype=float)
        counts[b] = float(np.mean(samp))

    p_one = float(np.mean(counts >= obs))
    return {
        "observed_mean": obs,
        "p_value_one_sided": p_one,
        "bootstrap_mean": float(np.mean(counts)),
        "bootstrap_std": float(np.std(counts, ddof=1)),
        "n_bootstrap": n_bootstrap,
        "block_len": block_len,
    }
