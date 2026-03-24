# EquiSense SLO / SLI Baseline

This document defines service-level targets for the current stage of the platform.

## Scope

- Data refresh flows (`/api/v1/stocks/*`, `/api/v1/jobs/*`, batch scripts)
- Prediction API (`/api/v1/predictions/*`)
- Local data artifacts (`data/raw`, `data/processed`)

## SLI and SLO

1. **Quote Freshness**
   - **SLI:** age of `data/raw/quotes/{TICKER}.json` at response time.
   - **SLO:** p95 freshness <= 120 seconds during market hours.

2. **OHLCV Daily Freshness**
   - **SLI:** latest `date` in `raw/ohlcv/{TICKER}.parquet` after scheduled refresh.
   - **SLO:** 99% of tracked tickers updated to last market day by T+1 06:00 UTC.

3. **Batch Refresh Success Rate**
   - **SLI:** `success / tickers_total` per run from `refresh_metrics_<run_id>.json`.
   - **SLO:** >= 95% success rate per run; failures retried up to configured attempts.

4. **Prediction Endpoint Latency**
   - **SLI:** `/api/v1/predictions/{ticker}` request duration.
   - **SLO:** p95 <= 1.5s on warm cache and model artifacts present.

5. **Error Budget**
   - **SLI:** non-2xx response ratio for `/api/v1/*` excluding explicit 4xx user input errors.
   - **SLO:** <= 1% per rolling 7-day window.

## Alerting Baseline

- Alert when:
  - two consecutive batch runs have success rate < 90%
  - quote freshness breaches SLO for > 10 minutes
  - prediction non-2xx breaches 2% for 15 minutes

## Notes

- These targets are baseline and should evolve with production usage.
- Migration triggers and architecture evolution remain in `ARCHITECTURE_DECISIONS.md`.

