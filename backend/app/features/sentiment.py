"""News → daily sentiment features via FinBERT (ProsusAI/finbert), inference only."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from app.core.config import settings


def _finbert_device() -> Any:
    import torch

    raw = (settings.finbert_device or "auto").strip().lower()
    if raw == "cuda":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if raw == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _normalize_published(item: dict[str, Any]) -> pd.Timestamp | None:
    s = item.get("published_at")
    if not s or not isinstance(s, str):
        return None
    try:
        ts = pd.to_datetime(s, utc=True)
        if pd.isna(ts):
            return None
        return ts.normalize()
    except (ValueError, TypeError):
        return None


def _price_dates_index(price_dates: Any) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """UTC-normalized index for rolling logic + naive index for Parquet output."""
    s = pd.Series(price_dates)
    idx = pd.DatetimeIndex(pd.to_datetime(s, utc=True)).normalize()
    naive = idx.tz_convert(None) if idx.tz is not None else idx
    return idx, naive


def _article_text(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "").strip()
    body = str(item.get("content") or "").strip()
    if title and body:
        return f"{title}. {body}"[:4000]
    return (title or body)[:4000]


class SentimentFeatureEngineer:
    """
    FinBERT sequence classification → per-article scores, then rolling daily aggregates
    aligned to trading dates from technical features.

    Outputs match SENTIMENT_FEATURES in constants.py.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.finbert_model_name
        self._model: Any = None
        self._tokenizer: Any = None
        self._device: Any = None
        self._pos_idx: int | None = None
        self._neg_idx: int | None = None

    def _load_model(self) -> None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if self._model is not None:
            return
        self._device = _finbert_device()
        logger.info("Loading FinBERT {} on {}", self.model_name, self._device)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self._model.to(self._device)
        self._model.eval()

        id2label = getattr(self._model.config, "id2label", None) or {}
        label_to_idx = {str(v).lower(): int(k) for k, v in id2label.items()}
        pos = label_to_idx.get("positive")
        neg = label_to_idx.get("negative")
        if pos is None or neg is None:
            raise RuntimeError(
                f"Unexpected FinBERT labels {id2label!r}; expected positive and negative"
            )
        self._pos_idx = pos
        self._neg_idx = neg

    def score_text(self, text: str) -> dict[str, Any]:
        return self.score_batch([text])[0]

    def score_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        import torch

        self._load_model()
        assert self._model is not None and self._tokenizer is not None
        assert self._device is not None and self._pos_idx is not None and self._neg_idx is not None

        cleaned = [t.strip() or " " for t in texts]
        batch_size = max(1, int(settings.finbert_batch_size))
        out: list[dict[str, Any]] = []

        with torch.no_grad():
            for start in range(0, len(cleaned), batch_size):
                chunk = cleaned[start : start + batch_size]
                enc = self._tokenizer(
                    chunk,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                )
                enc = {k: v.to(self._device) for k, v in enc.items()}
                logits = self._model(**enc).logits
                probs = torch.softmax(logits, dim=-1)
                pred_ids = torch.argmax(probs, dim=-1).tolist()
                for i in range(len(chunk)):
                    p = probs[i]
                    pos_p = float(p[self._pos_idx].item())
                    neg_p = float(p[self._neg_idx].item())
                    score = pos_p - neg_p
                    pid = int(pred_ids[i])
                    label = str(self._model.config.id2label.get(pid, "neutral")).lower()
                    out.append({"label": label, "score": score})
        return out

    def compute(
        self,
        news_list: list[dict[str, Any]],
        price_dates: pd.Series | pd.DatetimeIndex | Any,
        window: int = 3,
    ) -> pd.DataFrame:
        """
        Build one row per trading day in price_dates (same order as technical index).

        Rolling window: calendar days backward from each row's date (inclusive).
        """
        dates_utc, dates_out = _price_dates_index(price_dates)
        if len(dates_utc) == 0:
            raise ValueError("price_dates must be non-empty")

        n = len(dates_utc)
        if not news_list:
            return pd.DataFrame(
                {
                    "date": dates_out,
                    "sentiment_score": np.zeros(n, dtype=float),
                    "news_count": np.zeros(n, dtype=int),
                    "positive_ratio": np.zeros(n, dtype=float),
                    "negative_ratio": np.zeros(n, dtype=float),
                    "sentiment_momentum": np.zeros(n, dtype=float),
                }
            )

        rows: list[dict[str, Any]] = []
        texts: list[str] = []
        for item in news_list:
            d = _normalize_published(item)
            if d is None:
                continue
            t = _article_text(item)
            if not t.strip():
                continue
            texts.append(t)
            rows.append({"date": d, "text": t})

        if not rows:
            return pd.DataFrame(
                {
                    "date": dates_out,
                    "sentiment_score": np.zeros(n, dtype=float),
                    "news_count": np.zeros(n, dtype=int),
                    "positive_ratio": np.zeros(n, dtype=float),
                    "negative_ratio": np.zeros(n, dtype=float),
                    "sentiment_momentum": np.zeros(n, dtype=float),
                }
            )

        scored = self.score_batch(texts)
        for r, s in zip(rows, scored, strict=True):
            r["score"] = float(s["score"])
            r["label"] = str(s["label"])

        art_df = pd.DataFrame(rows)
        art_df["day"] = art_df["date"].dt.normalize()

        scores: list[float] = []
        counts: list[int] = []
        pos_ratios: list[float] = []
        neg_ratios: list[float] = []

        window = max(1, int(window))

        for d in dates_utc:
            d_n = d
            start = d_n - pd.Timedelta(days=window - 1)
            mask = (art_df["day"] >= start) & (art_df["day"] <= d_n)
            sub = art_df.loc[mask]
            c = int(len(sub))
            counts.append(c)
            if c == 0:
                scores.append(0.0)
                pos_ratios.append(0.0)
                neg_ratios.append(0.0)
                continue
            scores.append(float(sub["score"].mean()))
            pos_ratios.append(float((sub["label"] == "positive").mean()))
            neg_ratios.append(float((sub["label"] == "negative").mean()))

        momentum: list[float] = []
        for i, d in enumerate(dates_utc):
            past = d - pd.Timedelta(days=window)
            mask_p = (art_df["day"] >= past - pd.Timedelta(days=window - 1)) & (
                art_df["day"] <= past
            )
            sub_p = art_df.loc[mask_p]
            if len(sub_p) == 0:
                momentum.append(0.0)
            else:
                prev_mean = float(sub_p["score"].mean())
                momentum.append(float(scores[i] - prev_mean) if not math.isnan(scores[i]) else 0.0)

        out_df = pd.DataFrame(
            {
                "date": dates_out,
                "sentiment_score": scores,
                "news_count": counts,
                "positive_ratio": pos_ratios,
                "negative_ratio": neg_ratios,
                "sentiment_momentum": momentum,
            }
        )
        return out_df.reset_index(drop=True)
