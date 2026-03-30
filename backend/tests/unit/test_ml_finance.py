from __future__ import annotations

import numpy as np

from app.domain.identifiers import ROLLOUT_MODEL_IDS
from app.ml.cv import (
    _purge_train_by_label_overlap,
    combinatorial_purged_cv_splits,
    purged_kfold_splits,
    purged_kfold_with_horizon,
    walk_forward_expanding_splits,
)
from app.ml.finance_stats import diebold_mariano, max_drawdown, net_returns_with_transaction_costs
from app.ml.meta_labeling import apply_meta_gating
from app.ml.spa_lite import block_bootstrap_mean_pvalue
from app.models import MODEL_REGISTRY


def test_walk_forward_splits_non_empty() -> None:
    d = np.arange("2020-01-01", "2022-01-01", dtype="datetime64[D]")
    splits = walk_forward_expanding_splits(d, n_splits=4)
    assert len(splits) >= 1
    tr, te = splits[0]
    assert len(tr) > 0 and len(te) > 0
    assert tr.max() < te.min()


def test_purged_kfold_splits() -> None:
    d = np.arange("2020-01-01", "2021-06-01", dtype="datetime64[D]")
    splits = purged_kfold_splits(d, n_splits=5, embargo_days=3)
    assert len(splits) >= 1


def test_purged_kfold_horizon_splits() -> None:
    d = np.arange("2020-01-01", "2021-06-01", dtype="datetime64[D]")
    splits = purged_kfold_with_horizon(d, n_splits=5, label_horizon_days=2, embargo_days=3)
    assert len(splits) >= 1


def test_diebold_mariano_identical_losses() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    out = diebold_mariano(x, x, h=1)
    assert abs(out["mean_d"]) < 1e-9
    assert out["p_value_two_sided"] > 0.5


def test_net_returns_costs() -> None:
    g = np.array([0.01, 0.02, -0.01, 0.0])
    pos = np.array([1.0, 1.0, 0.0, 1.0])
    net = net_returns_with_transaction_costs(g, pos, cost_per_turn=0.001)
    assert net.shape == g.shape
    assert net[1] == g[1]  # no position change


def test_max_drawdown() -> None:
    eq = np.array([1.0, 1.2, 1.1, 0.9, 1.0])
    assert max_drawdown(eq) < 0


def test_apply_meta_gating_shape() -> None:
    p1 = np.array([0.6, 0.4, 0.7])
    pm = np.array([0.8, 0.9, 0.3])
    pos = apply_meta_gating(p1, pm, primary_threshold=0.5, meta_threshold=0.5)
    assert pos.tolist() == [1.0, 0.0, 0.0]


def test_purge_train_by_label_overlap_removes_leaky_indices() -> None:
    train_pos = {0, 2, 3, 10}
    test_pos = {4, 5}
    n = 20
    kept = _purge_train_by_label_overlap(
        train_pos, test_pos, label_horizon_days=1, embargo_days=0, n_dates=n
    )
    assert 3 not in kept
    assert {0, 2, 10}.issubset(kept)


def test_rollout_models_registered() -> None:
    for mid in ROLLOUT_MODEL_IDS:
        assert mid in MODEL_REGISTRY


def test_combinatorial_purged_cv_non_empty() -> None:
    d = np.arange("2015-01-01", "2023-01-01", dtype="datetime64[D]")
    splits = combinatorial_purged_cv_splits(
        d,
        n_groups=8,
        test_n_groups=2,
        embargo_days=5,
        label_horizon_days=1,
        max_splits=12,
        seed=0,
    )
    assert len(splits) >= 1
    tr, te = splits[0]
    assert len(tr) > 0 and len(te) > 0
    assert set(tr).isdisjoint(set(te))


def test_spa_lite_reproducible_and_observed_mean() -> None:
    rng = np.random.default_rng(0)
    spread = rng.normal(size=200)
    a = block_bootstrap_mean_pvalue(spread, n_bootstrap=300, block_len=5, seed=7)
    b = block_bootstrap_mean_pvalue(spread, n_bootstrap=300, block_len=5, seed=7)
    assert a == b
    assert abs(a["observed_mean"] - float(np.mean(spread))) < 1e-9
    assert 0.0 <= a["p_value_one_sided"] <= 1.0


def test_spa_lite_too_few_observations() -> None:
    out = block_bootstrap_mean_pvalue(np.array([0.01, 0.02]), n_bootstrap=100, block_len=5)
    assert out["p_value_one_sided"] == 1.0
    assert out.get("note") == "too_few_observations"
