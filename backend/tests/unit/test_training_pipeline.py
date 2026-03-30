"""Production training pipeline (imputer + imbalance)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV

from app.features.constants import TECHNICAL_FEATURES
from app.ml.training_pipeline import calibrate_production_model, fit_production_pipeline
from app.models.model_a import ModelA


def test_fit_production_pipeline_imputes_and_predicts() -> None:
    rng = np.random.default_rng(0)
    n = 120
    X = pd.DataFrame({f: rng.standard_normal(n) for f in TECHNICAL_FEATURES})
    X.iloc[:5, 0] = np.nan
    y = pd.Series(rng.integers(0, 2, size=n), name="target")
    m = ModelA()
    fit_production_pipeline(m, X, y)
    proba = m.predict_proba(X)
    assert proba.shape == (n, 2)
    assert np.all(np.isfinite(proba))


def test_calibrate_production_model_prefit_isotonic() -> None:
    rng = np.random.default_rng(1)
    n = 160
    X = pd.DataFrame({f: rng.standard_normal(n) for f in TECHNICAL_FEATURES})
    y = pd.Series(rng.integers(0, 2, size=n), name="target")
    m = ModelA()
    tr, va = slice(0, 100), slice(100, 150)
    fit_production_pipeline(m, X.iloc[tr], y.iloc[tr])
    status = calibrate_production_model(m, X.iloc[va], y.iloc[va])
    assert status == "isotonic_applied"
    assert isinstance(m.model, CalibratedClassifierCV)
    proba = m.predict_proba(X.iloc[150:])
    assert proba.shape == (10, 2)
