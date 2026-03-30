"""Загрузка OHLCV без Alpha Vantage / без лимитов «5 req/min».

Источники (по надёжности для курсовой / воспроизводимости):

1) **csv** — локальный файл после ручного скачивания с Kaggle / др.
   Подходящие датасеты (много тикеров, дневные бары, без ключа API):
   - `borismarjanovic/price-volume-data-for-all-us-stocks-etfs` (Huge Stock Market) —
     можно скачать отдельные `AAPL.csv` и т.д. через сайт Kaggle или CLI.
   - `qks1lver/amex-nyse-nasdaq-stock-histories` — истории по биржам.
2) **stooq** — прямой CSV с stooq.com (без ключа; иногда блокируется сетью/регионом).
3) **plotly-demo** — один тикер AAPL с raw.githubusercontent.com/plotly/datasets (для смоук-теста).

Примеры:

  cd backend
  uv run python scripts/download_ohlcv_dataset.py plotly-demo --run-etl

  uv run python scripts/download_ohlcv_dataset.py stooq --tickers AAPL MSFT --sleep 1

  uv run python scripts/download_ohlcv_dataset.py csv --path ~/Downloads/AAPL.csv --ticker AAPL

Требуемые колонки в Parquet: date, open, high, low, close, volume (см. app.data.validation).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.data.persistence import (  # noqa: E402
    fundamentals_json_path,
    ohlcv_parquet_path,
    write_news_json_sync,
)
from app.data.validation import validate_ohlcv_frame  # noqa: E402

PLOTLY_AAPL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/finance-charts-apple.csv"
)
_STOOQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EquiSenseData/1.0; +https://github.com/)",
    "Accept": "text/csv,*/*",
}


def _ensure_datetime_date(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, utc=False, errors="coerce")
    if getattr(out.dt, "tz", None) is not None:
        out = out.dt.tz_localize(None)
    return out


def normalize_ohlcv_frame(
    df: pd.DataFrame,
    *,
    ticker: str | None = None,
) -> pd.DataFrame:
    """Приводит к колонкам date, open, high, low, close, volume."""
    if df.empty:
        raise ValueError("empty dataframe")

    lower = {c.lower(): c for c in df.columns}

    def pick(*names: str) -> str | None:
        for n in names:
            if n in lower:
                return lower[n]
        return None

    # Plotly demo: Date, AAPL.Open, ...
    date_col = pick("date") or pick("datetime")
    if date_col is None:
        for c in df.columns:
            if str(c).lower().startswith("date") or str(c).endswith(".Date"):
                date_col = c
                break
    if date_col is None:
        raise ValueError("cannot detect date column")

    open_c = pick("open")
    high_c = pick("high")
    low_c = pick("low")
    close_c = pick("close")
    vol_c = pick("volume")

    if ticker and open_c is None:
        t = ticker.upper()
        for col in df.columns:
            u = str(col).upper()
            if u.endswith(".OPEN") and t in u.split(".")[0].upper():
                open_c = col
            elif u.endswith(".HIGH") and t in u.split(".")[0].upper():
                high_c = col
            elif u.endswith(".LOW") and t in u.split(".")[0].upper():
                low_c = col
            elif u.endswith(".CLOSE") and t in u.split(".")[0].upper():
                close_c = col
            elif u.endswith(".VOLUME") and t in u.split(".")[0].upper():
                vol_c = col

    missing = [x for x in (open_c, high_c, low_c, close_c, vol_c) if x is None]
    if missing:
        raise ValueError(f"cannot map OHLCV columns; missing={missing}")

    out = pd.DataFrame(
        {
            "date": _ensure_datetime_date(df[date_col]),
            "open": pd.to_numeric(df[open_c], errors="coerce"),
            "high": pd.to_numeric(df[high_c], errors="coerce"),
            "low": pd.to_numeric(df[low_c], errors="coerce"),
            "close": pd.to_numeric(df[close_c], errors="coerce"),
            "volume": pd.to_numeric(df[vol_c], errors="coerce"),
        }
    )
    out = out.dropna(subset=["date", "open", "high", "low", "close"])
    out = out.sort_values("date").reset_index(drop=True)
    # volume may be NaN for some rows; fill with 0 for int-like
    out["volume"] = out["volume"].fillna(0).astype("int64", copy=False)
    return out


def fetch_stooq_daily(ticker: str) -> pd.DataFrame:
    sym = f"{ticker.strip().lower()}.us"
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=_STOOQ_HEADERS) as client:
        r = client.get(url)
        r.raise_for_status()
        text = r.text
    if not text or not text.strip():
        raise RuntimeError(
            "Stooq вернул пустой ответ (часто из-за сети/гео/прокси). "
            "Используйте plotly-demo, csv с Kaggle или VPN."
        )
    if "html" in (r.headers.get("content-type") or "").lower() and "<html" in text[:200].lower():
        raise RuntimeError("Stooq вернул HTML вместо CSV — попробуйте другой источник.")
    df = pd.read_csv(StringIO(text))
    return normalize_ohlcv_frame(df, ticker=ticker)


def fetch_plotly_aapl_demo() -> pd.DataFrame:
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=_STOOQ_HEADERS) as client:
        r = client.get(PLOTLY_AAPL)
        r.raise_for_status()
        text = r.text
    df = pd.read_csv(StringIO(text))
    return normalize_ohlcv_frame(df, ticker="AAPL")


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def import_csv(
    path: Path,
    *,
    ticker: str,
    symbol_col: str | None,
) -> pd.DataFrame:
    raw = _read_csv(path)
    if symbol_col and symbol_col in raw.columns:
        sym = ticker.strip().upper()
        raw = raw[raw[symbol_col].astype(str).str.upper() == sym]
        if raw.empty:
            raise ValueError(f"no rows for symbol {sym!r} in column {symbol_col!r}")
    return normalize_ohlcv_frame(raw, ticker=ticker)


def write_ohlcv_parquet_sync(ticker: str, df: pd.DataFrame) -> Path:
    sym = ticker.strip().upper()
    validate_ohlcv_frame(df, context=f"raw/ohlcv/{sym}")
    p = ohlcv_parquet_path(sym)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return p


def write_minimal_fundamentals(ticker: str) -> Path:
    """Минимальный JSON для ETL (OVERVIEW можно позже подставить из API)."""
    sym = ticker.strip().upper()
    payload: dict[str, Any] = {
        "Symbol": sym,
        "Name": sym,
    }
    p = fundamentals_json_path(sym)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def write_empty_news(ticker: str) -> None:
    write_news_json_sync(ticker.strip().upper(), [])


def run_etl_for(tickers: list[str]) -> None:
    from app.etl.pipeline import RawToProcessedETL

    etl = RawToProcessedETL()
    for t in tickers:
        sym = t.strip().upper()
        etl.run_technical(sym)
        etl.run_fundamental(sym)
        etl.run_sentiment(sym)
        print("ETL ok", sym)


def main() -> None:
    p = argparse.ArgumentParser(description="Загрузка OHLCV в data/raw без лимитов API")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_demo = sub.add_parser("plotly-demo", help="AAPL с GitHub (Plotly), без ключей")
    sp_demo.add_argument("--run-etl", action="store_true")

    sp_stooq = sub.add_parser("stooq", help="Дневные бары со Stooq (.us)")
    sp_stooq.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "JNJ", "V"],
    )
    sp_stooq.add_argument("--sleep", type=float, default=0.5, help="Пауза между тикерами, сек")
    sp_stooq.add_argument("--run-etl", action="store_true")

    sp_csv = sub.add_parser("csv", help="Импорт из локального CSV (Kaggle и др.)")
    sp_csv.add_argument("--path", type=Path, required=True)
    sp_csv.add_argument("--ticker", required=True, help="Имя тикера для имени файла Parquet")
    sp_csv.add_argument(
        "--symbol-column",
        default=None,
        help="Колонка с тикером (для long-format: отфильтровать один символ)",
    )
    sp_csv.add_argument("--run-etl", action="store_true")

    args = p.parse_args()

    if args.cmd == "plotly-demo":
        df = fetch_plotly_aapl_demo()
        path = write_ohlcv_parquet_sync("AAPL", df)
        write_minimal_fundamentals("AAPL")
        write_empty_news("AAPL")
        print(" wrote", path, "rows", len(df))
        if args.run_etl:
            run_etl_for(["AAPL"])
        return

    if args.cmd == "stooq":
        ok: list[str] = []
        for t in args.tickers:
            sym = t.strip().upper()
            try:
                df = fetch_stooq_daily(sym)
                path = write_ohlcv_parquet_sync(sym, df)
                write_minimal_fundamentals(sym)
                write_empty_news(sym)
                print(" wrote", path, "rows", len(df))
                ok.append(sym)
            except Exception as e:  # noqa: BLE001
                print(f" FAIL {sym}: {e}", file=sys.stderr)
            time.sleep(max(0.0, args.sleep))
        if args.run_etl and ok:
            run_etl_for(ok)
        return

    if args.cmd == "csv":
        df = import_csv(args.path, ticker=args.ticker, symbol_col=args.symbol_column)
        sym = args.ticker.strip().upper()
        path = write_ohlcv_parquet_sync(sym, df)
        write_minimal_fundamentals(sym)
        write_empty_news(sym)
        print(" wrote", path, "rows", len(df))
        if args.run_etl:
            run_etl_for([sym])
        return


if __name__ == "__main__":
    main()
