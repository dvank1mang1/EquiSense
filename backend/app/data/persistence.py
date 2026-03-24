"""Local raw cache (Parquet / JSON) — reproducibility and fewer API calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pandas as pd

from app.core.config import settings


def data_root(override: Path | None = None) -> Path:
    if override is not None:
        return override.resolve()
    return Path(settings.model_dir).resolve().parent


def ohlcv_dir(root: Path | None = None) -> Path:
    return data_root(root) / "raw" / "ohlcv"


def ohlcv_parquet_path(ticker: str, *, root: Path | None = None) -> Path:
    return ohlcv_dir(root) / f"{ticker.upper()}.parquet"


def fundamentals_json_path(ticker: str, *, root: Path | None = None) -> Path:
    return data_root(root) / "raw" / "fundamentals" / f"{ticker.upper()}.json"


def quotes_dir(root: Path | None = None) -> Path:
    return data_root(root) / "raw" / "quotes"


def quote_json_path(ticker: str, *, root: Path | None = None) -> Path:
    return quotes_dir(root) / f"{ticker.upper()}.json"


def news_json_path(ticker: str, *, root: Path | None = None) -> Path:
    return data_root(root) / "raw" / "news" / f"{ticker.upper()}.json"


def read_news_json_sync(ticker: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    path = news_json_path(ticker, root=root)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return cast(list[dict[str, Any]], data)
    return []


def write_news_json_sync(
    ticker: str, items: list[dict[str, Any]], *, root: Path | None = None
) -> Path:
    path = news_json_path(ticker, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    return path


def read_ohlcv_parquet_sync(ticker: str, *, root: Path | None = None) -> pd.DataFrame | None:
    path = ohlcv_parquet_path(ticker, root=root)
    if not path.exists():
        return None
    return pd.read_parquet(path)


async def read_ohlcv_parquet(ticker: str, *, root: Path | None = None) -> pd.DataFrame | None:
    path = ohlcv_parquet_path(ticker, root=root)
    if not path.exists():
        return None

    def _read() -> pd.DataFrame:
        return pd.read_parquet(path)

    return await asyncio.to_thread(_read)


async def write_ohlcv_parquet(ticker: str, df: pd.DataFrame, *, root: Path | None = None) -> Path:
    path = ohlcv_parquet_path(ticker, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write() -> None:
        df.to_parquet(path, index=False)

    await asyncio.to_thread(_write)
    return path


async def list_cached_ohlcv_tickers(*, root: Path | None = None) -> list[str]:
    def _list() -> list[str]:
        d = ohlcv_dir(root)
        if not d.exists():
            return []
        return sorted({p.stem.upper() for p in d.glob("*.parquet")})

    return await asyncio.to_thread(_list)


async def read_fundamentals_json(ticker: str, *, root: Path | None = None) -> dict | None:
    path = fundamentals_json_path(ticker, root=root)
    if not path.exists():
        return None

    def _read() -> dict[str, Any]:
        with path.open(encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))

    return await asyncio.to_thread(_read)


async def write_fundamentals_json(ticker: str, payload: dict, *, root: Path | None = None) -> Path:
    path = fundamentals_json_path(ticker, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write() -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    await asyncio.to_thread(_write)
    return path
