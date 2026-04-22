from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, roc_auc_score


@dataclass
class TrainedResearchModel:
    model_type: str
    imputer: SimpleImputer
    model: object

    def predict_score(self, frame: pd.DataFrame, feature_columns: list[str]) -> np.ndarray:
        x = frame.reindex(columns=feature_columns)
        xi = self.imputer.transform(x)
        if self.model_type == "classification":
            model = self.model
            if not hasattr(model, "predict_proba"):
                raise ValueError("classification model does not expose predict_proba")
            proba = model.predict_proba(xi)[:, 1]
            return np.asarray(proba, dtype=float)
        preds = self.model.predict(xi)
        return np.asarray(preds, dtype=float)


def _build_lgbm_classifier() -> object:
    from lightgbm import LGBMClassifier

    return LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=63,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        verbosity=-1,
    )


def _build_lgbm_regressor() -> object:
    from lightgbm import LGBMRegressor

    return LGBMRegressor(
        n_estimators=350,
        learning_rate=0.05,
        num_leaves=63,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        verbosity=-1,
    )


def _build_lgbm_ranker() -> object:
    from lightgbm import LGBMRanker

    return LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=350,
        learning_rate=0.05,
        num_leaves=63,
        random_state=42,
        verbosity=-1,
    )


def _date_group_sizes(dates: pd.Series) -> list[int]:
    norm = pd.to_datetime(dates, errors="coerce").dt.normalize()
    return [int(v) for v in norm.value_counts(sort=False).sort_index().values]


def _rank_labels_per_date(train: pd.DataFrame) -> np.ndarray:
    # LambdaRank expects graded relevance; map fwd_5d ranks into [0..9].
    rel = train.groupby("date")["fwd_5d"].rank(method="first", pct=True)
    labels = np.clip(np.floor(rel * 10.0), 0, 9).astype(int)
    return labels.to_numpy()


def train_research_model(
    *,
    model_type: str,
    train_df: pd.DataFrame,
    feature_columns: list[str],
) -> TrainedResearchModel:
    x = train_df.reindex(columns=feature_columns)
    imputer = SimpleImputer(strategy="median")
    xi = imputer.fit_transform(x)

    mode = model_type.strip().lower()
    if mode == "classification":
        y = train_df["target_cls"].astype(int).to_numpy()
        model = _build_lgbm_classifier()
        model.fit(xi, y)
        return TrainedResearchModel(model_type=mode, imputer=imputer, model=model)
    if mode == "regression":
        y = pd.to_numeric(train_df["fwd_5d"], errors="coerce").to_numpy()
        model = _build_lgbm_regressor()
        model.fit(xi, y)
        return TrainedResearchModel(model_type=mode, imputer=imputer, model=model)
    if mode == "ranking":
        y = _rank_labels_per_date(train_df)
        group = _date_group_sizes(train_df["date"])
        model = _build_lgbm_ranker()
        model.fit(xi, y, group=group)
        return TrainedResearchModel(model_type=mode, imputer=imputer, model=model)
    raise ValueError(f"unsupported model_type: {model_type!r}")


def classification_aux_metrics(y_true: pd.Series, score: pd.Series) -> dict[str, float]:
    yt = pd.to_numeric(y_true, errors="coerce").astype(float).to_numpy()
    ys = pd.to_numeric(score, errors="coerce").astype(float).to_numpy()
    mask = np.isfinite(yt) & np.isfinite(ys)
    yt = yt[mask]
    ys = ys[mask]
    if len(yt) < 5 or len(np.unique(yt)) < 2:
        return {
            "roc_auc": float("nan"),
            "pr_auc": float("nan"),
            "class_prevalence": float(np.mean(yt)) if len(yt) > 0 else float("nan"),
            "pr_auc_vs_baseline": float("nan"),
        }
    roc = float(roc_auc_score(yt, ys))
    pr = float(average_precision_score(yt, ys))
    prev = float(np.mean(yt))
    return {
        "roc_auc": roc,
        "pr_auc": pr,
        "class_prevalence": prev,
        "pr_auc_vs_baseline": float(pr - prev),
    }
