"""Загрузка OHLCV без Alpha Vantage / без лимитов «5 req/min».

Источники (по надёжности для курсовой / воспроизводимости):

1) **csv** — локальный файл после ручного скачивания с Kaggle / др.
   Подходящие датасеты (много тикеров, дневные бары, без ключа API):
   - `borismarjanovic/price-volume-data-for-all-us-stocks-etfs` (Huge Stock Market) —
     можно скачать отдельные `AAPL.csv` и т.д. через сайт Kaggle или CLI.
   - `qks1lver/amex-nyse-nasdaq-stock-histories` — истории по биржам.
2) **stooq** — CSV с stooq.com; для массовой выдачи нужен **STOOQ_API_KEY** (см. сообщение сайта / captcha).
3) **plotly-demo** — один тикер AAPL с raw.githubusercontent.com/plotly/datasets (для смоук-теста).
4) **public-sample** — готовый long-format CSV (Vega Datasets / jsDelivr): AAPL, MSFT, AMZN, GOOG, IBM без ключей; цена → O=H=L=C, объём-заглушка (демо/UI).
5) **yfinance** — OHLCV + базовый фундаментал через `yfinance` (без Alpha Vantage; удобно для Docker: тот же `./data`, что в compose).
6) В режиме **`yfinance --source auto`** (по умолчанию): сначала Yahoo, затем Stooq, затем **Alpha Vantage**, если задан **`ALPHA_VANTAGE_API_KEY`** (актуально для Docker, когда Yahoo отдаёт HTML).

Примеры:

  cd backend
  uv run python scripts/download_ohlcv_dataset.py public-sample --run-etl

  uv run python scripts/download_ohlcv_dataset.py plotly-demo --run-etl

  uv run python scripts/download_ohlcv_dataset.py stooq --tickers AAPL MSFT --sleep 1

  uv run python scripts/download_ohlcv_dataset.py csv --path ~/Downloads/AAPL.csv --ticker AAPL

  # Kaggle borismarjanovic/price-volume-data-for-all-us-stocks-etfs (после unzip — Data/Stocks/*.us.txt):
  uv run python scripts/download_ohlcv_dataset.py kaggle-boris \
    --root ./kaggle-price-volume --tickers AAPL MSFT NVDA --run-etl

  # Один общий long CSV (другие датасеты), чанками:
  uv run python scripts/download_ohlcv_dataset.py kaggle-long \
    --path ~/Downloads/full_history.csv --tickers AAPL MSFT NVDA --run-etl

  # Рекомендуется для полного UI без AV (популярные тикеры + ETL в data/processed):
  uv run python scripts/download_ohlcv_dataset.py yfinance --tickers AAPL MSFT GOOGL TSLA AMZN NVDA META JPM --run-etl
  # Если Yahoo режет запросы — fallback на Stooq (нужен export STOOQ_API_KEY=...):
  uv run python scripts/download_ohlcv_dataset.py yfinance --source stooq --tickers AAPL MSFT --run-etl

  # Только Alpha Vantage (медленно: ~5 req/min на free tier; зато стабильно из контейнера):
  export ALPHA_VANTAGE_API_KEY=...
  uv run python scripts/download_ohlcv_dataset.py yfinance --source alpha_vantage --tickers AAPL MSFT --run-etl

Требуемые колонки в Parquet: date, open, high, low, close, volume (см. app.data.validation).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any, cast

import httpx
import pandas as pd

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_ROOT / ".env")
load_dotenv(_BACKEND_ROOT.parent / ".env")

from app.core.config import settings  # noqa: E402
from app.data.market_data import (  # noqa: E402
    ALPHA_BASE,
    _check_alpha_payload,
    _daily_series_to_df,
)
from app.data.persistence import (  # noqa: E402
    fundamentals_json_path,
    ohlcv_parquet_path,
    write_news_json_sync,
)
from app.data.utils import normalize_ticker  # noqa: E402
from app.data.validation import validate_ohlcv_frame  # noqa: E402
from app.domain.exceptions import UpstreamRateLimitError  # noqa: E402

# Пауза между запросами Alpha Vantage при массовой загрузке (один глобальный таймер).
_av_last_fetch_monotonic: float = 0.0

PLOTLY_AAPL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/finance-charts-apple.csv"
)
# Long-format monthly «price» (не настоящий intraday OHLCV); стабильное зеркало без API-ключей.
VEGA_STOCKS_CSV = (
    "https://cdn.jsdelivr.net/gh/vega/vega-datasets@v2.8.0/data/stocks.csv"
)
# Запрошенный тикер → символ в колонке Vega `symbol` (там GOOG, не GOOGL).
_VEGA_SYMBOL_ALIASES: dict[str, str] = {
    "GOOGL": "GOOG",
}
_VEGA_PLACEHOLDER_VOLUME = 1_000_000
_STOOQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EquiSenseData/1.0; +https://github.com/)",
    "Accept": "text/csv,*/*",
}

_STOOQ_KEY_PAGE_MARKER = "Get your apikey"


def _stooq_api_key() -> str | None:
    k = os.environ.get("STOOQ_API_KEY", "").strip()
    return k or None


def _parse_stooq_csv_text(text: str, *, ticker: str) -> pd.DataFrame:
    """Разбирает тело ответа Stooq: отсекает преамбулу, устойчив к мусорным строкам."""
    raw = text.strip()
    if not raw:
        raise RuntimeError(
            "Stooq вернул пустой ответ. Проверьте сеть или задайте STOOQ_API_KEY и повторите."
        )
    if _STOOQ_KEY_PAGE_MARKER in raw or (
        "captcha" in raw.lower() and "apikey" in raw.lower()
    ):
        raise RuntimeError(
            "Stooq отдал страницу с API-ключом вместо CSV. "
            "Откройте https://stooq.com/q/d/?s=aapl.us&get_apikey, пройдите captcha, "
            "скопируйте ключ в переменную окружения STOOQ_API_KEY и повторите загрузку. "
            "Иначе: импорт csv (Kaggle), plotly-demo (только AAPL), yfinance + VPN/curl_cffi."
        )
    lines = text.splitlines()
    header_idx: int | None = None
    for i, line in enumerate(lines):
        lead = line.lstrip("\ufeff").strip()
        if not lead:
            continue
        first_cell = lead.split(",", 1)[0].strip().lower()
        if first_cell == "date":
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError(
            "Stooq: не найдена строка заголовка CSV (колонка Date). "
            "Проверьте STOOQ_API_KEY или используйте другой источник данных."
        )
    body = "\n".join(lines[header_idx:])
    df = pd.read_csv(StringIO(body), engine="python", on_bad_lines="skip")
    return normalize_ohlcv_frame(df, ticker=ticker)


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
    q = f"s={sym}&i=d"
    key = _stooq_api_key()
    if key:
        q = f"{q}&apikey={key}"
    url = f"https://stooq.com/q/d/l/?{q}"
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=_STOOQ_HEADERS) as client:
        r = client.get(url)
        r.raise_for_status()
        text = r.text
    if "html" in (r.headers.get("content-type") or "").lower() and "<html" in text[:500].lower():
        raise RuntimeError("Stooq вернул HTML вместо CSV — попробуйте другой источник или STOOQ_API_KEY.")
    return _parse_stooq_csv_text(text, ticker=ticker)


def fetch_plotly_aapl_demo() -> pd.DataFrame:
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=_STOOQ_HEADERS) as client:
        r = client.get(PLOTLY_AAPL)
        r.raise_for_status()
        text = r.text
    df = pd.read_csv(StringIO(text))
    return normalize_ohlcv_frame(df, ticker="AAPL")


def fetch_vega_stocks_long() -> pd.DataFrame:
    with httpx.Client(timeout=120.0, follow_redirects=True, headers=_STOOQ_HEADERS) as client:
        r = client.get(VEGA_STOCKS_CSV)
        r.raise_for_status()
        text = r.text
    return pd.read_csv(StringIO(text))


def vega_long_row_to_ohlcv(long_df: pd.DataFrame, *, ticker: str) -> pd.DataFrame:
    """
    Одна серия из Vega stocks.csv: колонки symbol, date, price.
    Строит синтетический OHLCV (open=high=low=close=price) и фиксированный volume для пайплайна.
    """
    want = ticker.strip().upper()
    vega_sym = _VEGA_SYMBOL_ALIASES.get(want, want)
    if "symbol" not in long_df.columns:
        raise ValueError("Vega CSV: ожидается колонка symbol")
    sub = long_df[long_df["symbol"].astype(str).str.upper() == vega_sym].copy()
    if sub.empty:
        have = sorted(long_df["symbol"].astype(str).str.upper().unique().tolist())
        raise ValueError(
            f"Vega stocks: нет рядов для {want!r} (в файле символы {have}). "
            f"Для GOOGL используйте тикер из списка или алиас уже подставляет GOOG."
        )
    price = pd.to_numeric(sub["price"], errors="coerce")
    dt = _ensure_datetime_date(sub["date"])
    out = pd.DataFrame(
        {
            "date": dt,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": _VEGA_PLACEHOLDER_VOLUME,
        }
    )
    out = out.dropna(subset=["date", "close"])
    out = out.sort_values("date").reset_index(drop=True)
    out["volume"] = out["volume"].astype("int64", copy=False)
    if out.empty:
        raise ValueError(f"empty OHLCV after clean for {want}")
    return out


def fetch_yfinance_daily(ticker: str, *, period: str = "10y") -> pd.DataFrame:
    """
    Дневные бары Yahoo Finance (неофициальный API).

    Сначала `yf.download` (другой путь, чем `Ticker.history`; часто работает,
    когда JSON quote API отдаёт HTML и падает с «Expecting value»).
    Затем `Ticker.history`.
    """
    import yfinance as yf

    sym = ticker.strip().upper()
    last: str = ""

    try:
        raw = yf.download(
            sym,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
            ignore_tz=True,
        )
        if raw is not None and not raw.empty:
            if isinstance(raw.columns, pd.MultiIndex):
                raw = raw.copy()
                raw.columns = raw.columns.droplevel(1)
            df = raw.reset_index()
            return normalize_ohlcv_frame(df, ticker=sym)
    except Exception as e:  # noqa: BLE001
        last = str(e)

    try:
        hist = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=False)
        if hist is not None and not hist.empty:
            return normalize_ohlcv_frame(hist.reset_index(), ticker=sym)
    except Exception as e:  # noqa: BLE001
        last = str(e)

    hint = (
        " Yahoo часто режет запросы (HTML вместо JSON). Попробуйте: "
        "`export STOOQ_API_KEY=...` и `--source stooq`, `--source alpha_vantage` при "
        "`ALPHA_VANTAGE_API_KEY`, VPN, или `uv add curl_cffi`. В `--source auto` после "
        "Yahoo/Stooq вызывается Alpha Vantage, если ключ задан."
    )
    raise ValueError(f"yfinance: нет OHLCV для {sym}. {last}{hint}")


def fetch_alpha_vantage_daily(
    ticker: str,
    *,
    api_key: str,
    min_interval_sec: float,
    outputsize: str = "full",
    max_rate_limit_retries: int = 6,
) -> pd.DataFrame:
    """Синхронный TIME_SERIES_DAILY (полный ряд при outputsize=full).

    При ответе free-tier (Note / Information) — пауза и повтор: один ключ нельзя дёргать
    чаще ~5 раз/мин; параллельно API/воркер тоже расходуют лимит.
    """
    global _av_last_fetch_monotonic

    sym = normalize_ticker(ticker)
    key = api_key.strip()
    if not key:
        raise ValueError("ALPHA_VANTAGE_API_KEY is empty")

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": sym,
        "outputsize": outputsize,
        "apikey": key,
        "datatype": "json",
    }

    last_err: Exception | None = None
    for attempt in range(max(1, max_rate_limit_retries)):
        now = time.monotonic()
        wait = _av_last_fetch_monotonic + float(min_interval_sec) - now
        if wait > 0:
            time.sleep(wait)

        with httpx.Client(timeout=120.0) as client:
            r = client.get(ALPHA_BASE, params=params)
            r.raise_for_status()
            try:
                payload = cast(dict[str, Any], r.json())
            except json.JSONDecodeError as e:
                raise ValueError(f"Alpha Vantage: non-JSON body (status {r.status_code})") from e

        try:
            _check_alpha_payload(payload)
        except UpstreamRateLimitError as e:
            last_err = e
            # Free tier: часто просят подождать до минуты; не обновляем pacing до успеха.
            pause = 65.0 + float(attempt) * 5.0
            print(
                f"{sym}: Alpha Vantage лимит (попытка {attempt + 1}/{max_rate_limit_retries}), "
                f"пауза {pause:.0f}s…",
                file=sys.stderr,
            )
            time.sleep(pause)
            continue

        _av_last_fetch_monotonic = time.monotonic()
        ts_key = "Time Series (Daily)"
        if ts_key not in payload:
            raise ValueError(f"Alpha Vantage: no {ts_key} in response (check symbol or limits)")
        return _daily_series_to_df(payload[ts_key])

    if last_err is not None:
        raise last_err
    raise RuntimeError(f"Alpha Vantage: не удалось загрузить {sym}")


def fetch_ohlcv_auto(
    ticker: str,
    *,
    period: str = "10y",
    source: str = "auto",
    alpha_min_interval_sec: float | None = None,
    alpha_api_key_override: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Возвращает (dataframe, \"yfinance\"|\"stooq\"|\"alpha_vantage\").

    ``source``: ``auto`` (yfinance → stooq → alpha_vantage при наличии ключа),
    либо один источник.
    """
    sym = ticker.strip().upper()
    av_interval = float(
        alpha_min_interval_sec
        if alpha_min_interval_sec is not None
        else settings.alpha_vantage_min_interval_sec
    )
    av_key = (
        (alpha_api_key_override or "").strip()
        or os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
        or (settings.alpha_vantage_api_key or "").strip()
    )

    if source == "alpha_vantage":
        if not av_key:
            raise RuntimeError(
                "Нет ALPHA_VANTAGE_API_KEY. Сделайте одно из: "
                "(1) положите ключ в .env в корне репозитория (рядом с docker-compose.yml) и выполните "
                "`docker compose up -d backend` чтобы пересоздать контейнер; "
                "(2) проверьте: `docker compose exec backend printenv ALPHA_VANTAGE_API_KEY`; "
                "(3) разово: флаг `--alpha-api-key ...` у этой команды."
            )
        return fetch_alpha_vantage_daily(sym, api_key=av_key, min_interval_sec=av_interval), "alpha_vantage"
    if source == "stooq":
        return fetch_stooq_daily(sym), "stooq"
    if source == "yfinance":
        return fetch_yfinance_daily(sym, period=period), "yfinance"
    try:
        return fetch_yfinance_daily(sym, period=period), "yfinance"
    except Exception as yf_err:  # noqa: BLE001
        try:
            return fetch_stooq_daily(sym), "stooq"
        except Exception as st_err:  # noqa: BLE001
            if av_key:
                try:
                    return (
                        fetch_alpha_vantage_daily(
                            sym, api_key=av_key, min_interval_sec=av_interval
                        ),
                        "alpha_vantage",
                    )
                except Exception as av_err:  # noqa: BLE001
                    raise RuntimeError(
                        f"{sym}: yfinance failed ({yf_err}); stooq failed ({st_err}); "
                        f"alpha_vantage failed ({av_err})"
                    ) from av_err
            raise RuntimeError(
                f"{sym}: yfinance failed ({yf_err}); stooq failed ({st_err})"
            ) from st_err


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


def _detect_kaggle_symbol_column(columns: list[str]) -> str | None:
    """Имя колонки с тикером в типичных Kaggle long CSV (Name, Symbol, …)."""
    lower_map = {str(c).lower(): c for c in columns}
    for key in ("name", "symbol", "ticker", "tickers"):
        if key in lower_map:
            return lower_map[key]
    return None


def import_kaggle_long_csv(
    path: Path,
    *,
    ticker: str,
    symbol_column: str | None,
    chunksize: int = 200_000,
) -> pd.DataFrame:
    """
    Строка на (дата, тикер) — как ``full_history.csv`` в популярных датасетах Kaggle.
    Читает чанками, чтобы не грузить весь файл в RAM.
    """
    sym = ticker.strip().upper()
    reader = pd.read_csv(path, chunksize=chunksize)
    try:
        first = next(reader)
    except StopIteration as e:
        raise ValueError(f"empty CSV: {path}") from e

    sym_col = symbol_column or _detect_kaggle_symbol_column(list(first.columns))
    if not sym_col or sym_col not in first.columns:
        raise ValueError(
            f"не найдена колонка тикера; задайте --symbol-column. Колонки: {list(first.columns)}"
        )

    chunks: list[pd.DataFrame] = []

    def _take(frame: pd.DataFrame) -> None:
        sub = frame[frame[sym_col].astype(str).str.upper().str.strip() == sym]
        if not sub.empty:
            chunks.append(sub)

    _take(first)
    for chunk in reader:
        _take(chunk)

    if not chunks:
        raise ValueError(f"нет строк для тикера {sym!r} в {path} (колонка {sym_col!r})")
    raw = pd.concat(chunks, ignore_index=True)
    return normalize_ohlcv_frame(raw, ticker=sym)


def resolve_kaggle_boris_ticker_path(unzip_root: Path, ticker: str) -> Path:
    """
    Архив borismarjanovic/price-volume-data-for-all-us-stocks-etfs:
    ``Data/Stocks/aapl.us.txt`` или ``Data/ETFs/...``.
    """
    root = unzip_root.resolve()
    sym = ticker.strip().lower()
    for sub in ("Stocks", "ETFs"):
        p = root / "Data" / sub / f"{sym}.us.txt"
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"нет файла для {ticker.upper()}: ожидалось {root}/Data/Stocks/{sym}.us.txt "
        f"или Data/ETFs/{sym}.us.txt"
    )


def write_ohlcv_parquet_sync(ticker: str, df: pd.DataFrame, *, root: Path | None = None) -> Path:
    sym = ticker.strip().upper()
    validate_ohlcv_frame(df, context=f"raw/ohlcv/{sym}")
    p = ohlcv_parquet_path(sym, root=root)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return p


def write_minimal_fundamentals(ticker: str, *, root: Path | None = None) -> Path:
    """Минимальный JSON для ETL (OVERVIEW можно позже подставить из API)."""
    sym = ticker.strip().upper()
    payload: dict[str, Any] = {
        "Symbol": sym,
        "Name": sym,
    }
    p = fundamentals_json_path(sym, root=root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def write_fundamentals_yfinance(ticker: str, *, root: Path | None = None) -> Path:
    """Поля в стиле Alpha Vantage OVERVIEW (где возможно) из yfinance `.info`."""
    import yfinance as yf

    sym = ticker.strip().upper()
    info: dict[str, Any] = {}
    try:
        raw = yf.Ticker(sym).info
        if isinstance(raw, dict):
            info = raw
    except Exception:
        pass

    def as_str(v: Any) -> str | None:
        if v is None:
            return None
        return str(v)

    name = info.get("longName") or info.get("shortName") or info.get("name") or sym
    payload: dict[str, Any] = {
        "Symbol": sym,
        "Name": str(name),
        "Sector": as_str(info.get("sector")) or "",
        "Industry": as_str(info.get("industry")) or "",
    }
    optional_map = [
        ("MarketCapitalization", "marketCap"),
        ("PERatio", "trailingPE"),
        ("EPS", "trailingEps"),
        ("QuarterlyRevenueGrowthYOY", "revenueGrowth"),
        ("ReturnOnEquityTTM", "returnOnEquity"),
        ("DebtToEquityRatio", "debtToEquity"),
    ]
    for av_key, yf_key in optional_map:
        v = info.get(yf_key)
        if v is not None and str(v).strip() not in ("", "None", "nan"):
            payload[av_key] = as_str(v)
    p = fundamentals_json_path(sym, root=root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def write_empty_news(ticker: str, *, root: Path | None = None) -> None:
    write_news_json_sync(ticker.strip().upper(), [], root=root)


def run_etl_for(tickers: list[str], *, data_root: Path | None = None) -> None:
    from app.etl.pipeline import RawToProcessedETL

    etl = RawToProcessedETL(data_root=data_root)
    for t in tickers:
        sym = t.strip().upper()
        etl.run_technical(sym)
        etl.run_fundamental(sym)
        etl.run_sentiment(sym)
        print("ETL ok", sym)


def _default_data_root(cli: Path | None) -> Path:
    """Как в docker-compose: `<корень репозитория>/data`, а не backend/data."""
    if cli is not None:
        return cli.resolve()
    env = os.environ.get("EQUISENSE_DATA_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "data").resolve()


def main() -> None:
    p = argparse.ArgumentParser(description="Загрузка OHLCV в data/raw без лимитов API")
    p.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Каталог data (как ./data в docker-compose). Иначе env EQUISENSE_DATA_ROOT, иначе <repo>/data. Указывать до подкоманды (yfinance, …).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_demo = sub.add_parser("plotly-demo", help="AAPL с GitHub (Plotly), без ключей")
    sp_demo.add_argument("--run-etl", action="store_true")

    sp_pub = sub.add_parser(
        "public-sample",
        help="Vega stocks.csv (jsDelivr): несколько тикеров без ключей; месячные цены как синтетический OHLCV",
    )
    sp_pub.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL", "MSFT", "GOOGL", "AMZN", "IBM"],
        help="Доступны в файле: AAPL MSFT AMZN GOOG IBM; GOOGL подставляет ряд GOOG",
    )
    sp_pub.add_argument("--run-etl", action="store_true")

    sp_stooq = sub.add_parser(
        "stooq",
        help="Дневные бары со Stooq (.us); задайте env STOOQ_API_KEY (см. stooq.com get_apikey)",
    )
    sp_stooq.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "JNJ", "V"],
    )
    sp_stooq.add_argument("--sleep", type=float, default=0.5, help="Пауза между тикерами, сек")
    sp_stooq.add_argument("--run-etl", action="store_true")

    sp_csv = sub.add_parser(
        "csv",
        help="Импорт одного CSV (один тикер на файл или long-format с --symbol-column). Для огромного full_history.csv см. kaggle-long",
    )
    sp_csv.add_argument("--path", type=Path, required=True)
    sp_csv.add_argument("--ticker", required=True, help="Имя тикера для имени файла Parquet")
    sp_csv.add_argument(
        "--symbol-column",
        default=None,
        help="Колонка с тикером (для long-format: отфильтровать один символ)",
    )
    sp_csv.add_argument("--run-etl", action="store_true")

    sp_kaggle = sub.add_parser(
        "kaggle-long",
        help="Long CSV как Kaggle full_history.csv (чанками; колонка Name/Symbol + Date OHLCV)",
    )
    sp_kaggle.add_argument(
        "--path",
        type=Path,
        required=True,
        help="Путь к full_history.csv (или аналог после unzip)",
    )
    sp_kaggle.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="Тикеры для выгрузки в raw/ohlcv/{TICKER}.parquet",
    )
    sp_kaggle.add_argument(
        "--symbol-column",
        default=None,
        help="Колонка с тикером (по умолчанию: name, symbol или ticker)",
    )
    sp_kaggle.add_argument(
        "--chunksize",
        type=int,
        default=200_000,
        help="Строк за чанк при чтении CSV (меньше — меньше RAM)",
    )
    sp_kaggle.add_argument("--run-etl", action="store_true")

    sp_kb = sub.add_parser(
        "kaggle-boris",
        help="Распакованный borismarjanovic/price-volume-data (Data/Stocks/TICKER.us.txt)",
    )
    sp_kb.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Корень после unzip (внутри должны быть Data/Stocks/)",
    )
    sp_kb.add_argument("--tickers", nargs="+", required=True)
    sp_kb.add_argument("--run-etl", action="store_true")

    sp_yf = sub.add_parser(
        "yfinance",
        help="OHLCV + фундаментал через yfinance (без Alpha Vantage)",
    )
    sp_yf.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA", "META", "JPM"],
    )
    sp_yf.add_argument(
        "--period",
        default="10y",
        help="Интервал yfinance history, напр. 5y, 10y, max",
    )
    sp_yf.add_argument("--sleep", type=float, default=0.25, help="Пауза между тикерами, сек")
    sp_yf.add_argument("--run-etl", action="store_true")
    sp_yf.add_argument(
        "--alpha-min-interval",
        type=float,
        default=None,
        help="Пауза между вызовами Alpha Vantage, сек (по умолчанию из настроек API, free ~12)",
    )
    sp_yf.add_argument(
        "--alpha-api-key",
        type=str,
        default=None,
        help="Ключ Alpha Vantage на этот запуск (если в контейнере пустой printenv)",
    )
    sp_yf.add_argument(
        "--source",
        choices=["auto", "yfinance", "stooq", "alpha_vantage"],
        default="auto",
        help="auto: yfinance → Stooq → Alpha Vantage при ALPHA_VANTAGE_API_KEY; alpha_vantage: только AV",
    )

    args = p.parse_args()
    data_root = _default_data_root(args.data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    print("data_root =", data_root)

    if args.cmd == "plotly-demo":
        df = fetch_plotly_aapl_demo()
        path = write_ohlcv_parquet_sync("AAPL", df, root=data_root)
        write_minimal_fundamentals("AAPL", root=data_root)
        write_empty_news("AAPL", root=data_root)
        print(" wrote", path, "rows", len(df))
        if args.run_etl:
            run_etl_for(["AAPL"], data_root=data_root)
        return

    if args.cmd == "public-sample":
        long_df = fetch_vega_stocks_long()
        ok: list[str] = []
        for t in args.tickers:
            sym = t.strip().upper()
            try:
                df = vega_long_row_to_ohlcv(long_df, ticker=sym)
                path = write_ohlcv_parquet_sync(sym, df, root=data_root)
                write_minimal_fundamentals(sym, root=data_root)
                write_empty_news(sym, root=data_root)
                print(" wrote", path, "rows", len(df), "(Vega public-sample)")
                ok.append(sym)
            except Exception as e:  # noqa: BLE001
                print(f" FAIL {sym}: {e}", file=sys.stderr)
        if args.run_etl and ok:
            run_etl_for(ok, data_root=data_root)
        return

    if args.cmd == "stooq":
        ok: list[str] = []
        for t in args.tickers:
            sym = t.strip().upper()
            try:
                df = fetch_stooq_daily(sym)
                path = write_ohlcv_parquet_sync(sym, df, root=data_root)
                write_minimal_fundamentals(sym, root=data_root)
                write_empty_news(sym, root=data_root)
                print(" wrote", path, "rows", len(df))
                ok.append(sym)
            except Exception as e:  # noqa: BLE001
                print(f" FAIL {sym}: {e}", file=sys.stderr)
            time.sleep(max(0.0, args.sleep))
        if args.run_etl and ok:
            run_etl_for(ok, data_root=data_root)
        return

    if args.cmd == "csv":
        df = import_csv(args.path, ticker=args.ticker, symbol_col=args.symbol_column)
        sym = args.ticker.strip().upper()
        path = write_ohlcv_parquet_sync(sym, df, root=data_root)
        write_minimal_fundamentals(sym, root=data_root)
        write_empty_news(sym, root=data_root)
        print(" wrote", path, "rows", len(df))
        if args.run_etl:
            run_etl_for([sym], data_root=data_root)
        return

    if args.cmd == "kaggle-long":
        ok: list[str] = []
        for t in args.tickers:
            sym = t.strip().upper()
            try:
                df = import_kaggle_long_csv(
                    args.path,
                    ticker=sym,
                    symbol_column=args.symbol_column,
                    chunksize=max(10_000, int(args.chunksize)),
                )
                path = write_ohlcv_parquet_sync(sym, df, root=data_root)
                write_minimal_fundamentals(sym, root=data_root)
                write_empty_news(sym, root=data_root)
                print(" wrote", path, "rows", len(df), "(kaggle-long)")
                ok.append(sym)
            except Exception as e:  # noqa: BLE001
                print(f" FAIL {sym}: {e}", file=sys.stderr)
        if args.run_etl and ok:
            run_etl_for(ok, data_root=data_root)
        return

    if args.cmd == "kaggle-boris":
        ok: list[str] = []
        unzip_root = args.root
        for t in args.tickers:
            sym = t.strip().upper()
            try:
                txt_path = resolve_kaggle_boris_ticker_path(unzip_root, sym)
                df = import_csv(txt_path, ticker=sym, symbol_col=None)
                path = write_ohlcv_parquet_sync(sym, df, root=data_root)
                write_minimal_fundamentals(sym, root=data_root)
                write_empty_news(sym, root=data_root)
                print(" wrote", path, "rows", len(df), "from", txt_path)
                ok.append(sym)
            except Exception as e:  # noqa: BLE001
                print(f" FAIL {sym}: {e}", file=sys.stderr)
        if args.run_etl and ok:
            run_etl_for(ok, data_root=data_root)
        return

    if args.cmd == "yfinance":
        ok: list[str] = []
        for t in args.tickers:
            sym = t.strip().upper()
            try:
                df, src = fetch_ohlcv_auto(
                    sym,
                    period=args.period,
                    source=args.source,
                    alpha_min_interval_sec=args.alpha_min_interval,
                    alpha_api_key_override=args.alpha_api_key,
                )
                path = write_ohlcv_parquet_sync(sym, df, root=data_root)
                if src == "yfinance":
                    write_fundamentals_yfinance(sym, root=data_root)
                else:
                    write_minimal_fundamentals(sym, root=data_root)
                write_empty_news(sym, root=data_root)
                print(" wrote", path, "rows", len(df), "source=", src)
                ok.append(sym)
            except Exception as e:  # noqa: BLE001
                print(f" FAIL {sym}: {e}", file=sys.stderr)
            time.sleep(max(0.0, args.sleep))
        if args.run_etl and ok:
            run_etl_for(ok, data_root=data_root)
        return


if __name__ == "__main__":
    main()
