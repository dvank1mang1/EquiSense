"""Summarize on-disk raw + processed artifacts for a ticker (ops / debugging, no GPU)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.data.persistence import (
    data_root,
    fundamentals_json_path,
    news_json_path,
    ohlcv_parquet_path,
    quote_json_path,
)
from app.domain.identifiers import FeatureSlice
from app.features.feature_store import FeatureStore


def _path_stat(path: Path) -> dict[str, Any]:
    p = path.resolve()
    if not p.exists():
        return {"path": str(p), "exists": False}
    st = p.stat()
    age_sec = max(0.0, time.time() - st.st_mtime)
    return {
        "path": str(p),
        "exists": True,
        "size_bytes": int(st.st_size),
        "age_sec": round(age_sec, 3),
    }


def summarize_data_artifacts(ticker: str) -> dict[str, Any]:
    sym = ticker.strip().upper()
    root = data_root()
    store = FeatureStore()

    raw = {
        "ohlcv": _path_stat(ohlcv_parquet_path(sym)),
        "fundamentals": _path_stat(fundamentals_json_path(sym)),
        "quote": _path_stat(quote_json_path(sym)),
        "news": _path_stat(news_json_path(sym)),
    }
    processed = {
        "technical": _path_stat(store.path_for(sym, FeatureSlice.TECHNICAL.value)),
        "fundamental": _path_stat(store.path_for(sym, FeatureSlice.FUNDAMENTAL.value)),
        "sentiment": _path_stat(store.path_for(sym, FeatureSlice.SENTIMENT.value)),
    }
    return {
        "ticker": sym,
        "data_root": str(root),
        "model_dir": str(Path(settings.model_dir).resolve()),
        "raw": raw,
        "processed": processed,
    }
