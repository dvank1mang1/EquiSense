# Market data sources (EquiSense)

This repository keeps a single canonical OHLCV schema under `data/raw/ohlcv/{TICKER}.parquet` with columns `date, open, high, low, close, volume` (see `backend/app/data/validation.py`).

## Primary extension path (2021–2025+)

- **Script:** `backend/scripts/download_ohlcv_dataset.py` subcommand `yfinance`
- **Upstream:** Yahoo Finance via the `yfinance` library (unofficial; acceptable for local research and demos).
- **Adjusted prices:** downloads use `auto_adjust=False` so raw OHLC reflects splits/dividends in Yahoo’s convention; this matches the prior pipeline default.
- **Timezones:** `ignore_tz=True` / timezone-naive `date` columns to avoid silent offset shifts vs. the rest of the ETL (daily bars as calendar dates).
- **Explicit window:** pass `--start-date 2021-01-01 --end-date 2026-01-01` (end is exclusive in `yfinance`, so daily data through 2025-12-31 is included) instead of `--period`.

## Fallbacks (same schema)

- **Stooq** daily `.us` symbols (`STOOQ_API_KEY` often required for bulk CSV).
- **Alpha Vantage** `TIME_SERIES_DAILY` when `ALPHA_VANTAGE_API_KEY` is set (rate-limited; used as fallback in `fetch_ohlcv_auto`).
- **Vega public sample / Plotly demo:** tiny datasets for offline UI smoke tests only (not for research coverage).

## Kaggle file bundles (no in-process yfinance)

Use when you want **versioned files from Kaggle** instead of live Yahoo scraping.

1. Install the optional helper: `uv sync --group datasets` (adds [`kagglehub`](https://github.com/Kaggle/kagglehub)).
2. Import one OHLCV file per ticker (small downloads; no full 25 GB unzip):

```bash
cd backend
uv run --group datasets python scripts/download_ohlcv_dataset.py kagglehub-file \
  --handle jacksoncrow/stock-market-dataset \
  --path-template stocks/{ticker}.csv \
  --tickers AAPL MSFT NVDA \
  --merge-existing \
  --run-etl
```

- **`jacksoncrow/stock-market-dataset`**: public daily OHLCV under `stocks/{TICKER}.csv` through about **2020-04** (Yahoo-style columns: `Date`, `Open`, …, `Adj Close`, `Volume`).
- **`--merge-existing`**: merges with existing `data/raw/ohlcv/{TICKER}.parquet` on **calendar date** (dedupe, keep last). Use this to **fill holes** when you already have a recent tail from another source.
- **Boris layout** (older history, ends ~2017): `--handle borismarjanovic/price-volume-data-for-all-us-stocks-etfs` and `--path-template Data/Stocks/{ticker_lower}.us.txt`.

Other Kaggle OHLCV bundles often require a logged-in Kaggle account (`~/.kaggle/kaggle.json` or env). Point `--handle` / `--path-template` at any dataset that exposes one CSV (or `.us.txt`) per symbol.

**Note:** `tanavbajaj/yahoo-finance-all-stocks-dataset-daily-update` is also public per `TICKER.csv`, but the version visible without auth may lag; prefer handles you can refresh with your own Kaggle credentials if you need the latest calendar year.

## Validation

- `uv run python backend/scripts/print_ohlcv_coverage.py` — min/max dates and row counts per ticker.
- After download, run ETL (`--run-etl` or `POST .../jobs/refresh-universe` with `run_etl: true`) so `data/processed/{TICKER}/technical.parquet` exists for ML paths.

## Limitations

- Yahoo/Stooq availability and corporate-action handling are vendor-dependent; cross-vendor stitching is not performed automatically.
- Single-name IC/ranking metrics in training are weakly identified (one row per date); panel models would need a true cross-section.
