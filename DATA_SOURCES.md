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

## Validation

- `uv run python backend/scripts/print_ohlcv_coverage.py` — min/max dates and row counts per ticker.
- After download, run ETL (`--run-etl` or `POST .../jobs/refresh-universe` with `run_etl: true`) so `data/processed/{TICKER}/technical.parquet` exists for ML paths.

## Limitations

- Yahoo/Stooq availability and corporate-action handling are vendor-dependent; cross-vendor stitching is not performed automatically.
- Single-name IC/ranking metrics in training are weakly identified (one row per date); panel models would need a true cross-section.
