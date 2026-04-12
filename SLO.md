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

6. **Queue Dead-letter Rate**
   - **SLI:** share of dead-letter jobs in worker queue snapshot (`dead_letter / (completed + failed)`).
   - **SLO:** <= 1% in rolling 24h window.

7. **Queue Stale Running**
   - **SLI:** `stale_running` from `/api/v1/jobs/worker/health` snapshot.
   - **SLO:** 0 stale running jobs for more than 5 consecutive minutes.

## Alerting Baseline

- Alert when:
  - two consecutive batch runs have success rate < 90%
  - quote freshness breaches SLO for > 10 minutes
  - prediction non-2xx breaches 2% for 15 minutes
  - `stale_running > 0` for 5 minutes
  - `dead_letter > 0` for 10 minutes
  - queue failure rate > 10% for 15 minutes

## Prometheus/Grafana Mapping

- API request/error SLI panels and alerts use `http_requests_total` from FastAPI instrumentation.
- Latency SLI panels and alerts use `http_request_duration_seconds_bucket` with `histogram_quantile`.
- Current dashboard/alerts are scoped to `job="equisense-backend"` to avoid mixing with non-API targets.
- Prediction-specific SLO widgets rely on `handler=~"/api/v1/predictions.*"` labels.
- Queue SLOs (`dead_letter`, `stale_running`) remain document-level targets until dedicated Prometheus metrics are exposed.

## Notes

- These targets are baseline and should evolve with production usage.
- Migration triggers and architecture evolution remain in `ARCHITECTURE_DECISIONS.md`.

