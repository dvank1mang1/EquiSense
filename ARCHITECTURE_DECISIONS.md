# EquiSense Architecture Decisions

This document captures intentional trade-offs for current architecture, plus migration triggers.

## ADR-001: Raw and Processed Storage in Files (Parquet/JSON)

- **Status:** Accepted
- **Date:** 2026-03-24
- **Decision:** Keep `data/raw` and `data/processed` as filesystem-based storage.
- **Why now:**
  - Fast iteration for ML workflows (`pandas` + Parquet).
  - Low operational overhead during product discovery.
  - Easy reproducibility for backfills and local experiments.
- **Current layout:**
  - `data/raw/ohlcv/{TICKER}.parquet`
  - `data/raw/fundamentals/{TICKER}.json`
  - `data/raw/quotes/{TICKER}.json`
  - `data/processed/{TICKER}/...` (feature store)
- **Risks:**
  - Concurrent writers require discipline.
  - Query flexibility is lower than SQL for ad-hoc analytics.
  - Multi-instance backend needs shared storage conventions.

## ADR-002: Split Offline and Online Data Flows

- **Status:** Accepted
- **Date:** 2026-03-24
- **Decision:** Use two logical flows over one storage:
  - **Offline/batch** for historical updates (`full` then `compact+merge`).
  - **Online** for quote/fundamentals refresh with TTL.
- **Why now:**
  - Matches different freshness/cost requirements.
  - Works with Alpha Vantage free-tier limits.
- **Implementation notes:**
  - Shared API limiter (`~12s`) across market and fundamentals clients.
  - `POST /stocks/{ticker}/refresh` as explicit refresh control.

## ADR-003: Tooling Quality Gate (Ruff + MyPy + Pytest + CI)

- **Status:** Accepted
- **Date:** 2026-03-24
- **Decision:** Enforce lint/type/test checks for backend in CI and pre-commit.
- **Why now:**
  - Prevent quality drift while codebase grows quickly.
  - Keep changes reviewable and safer with explicit gates.

## ADR-004: Control-Plane Metadata in Postgres + Worker Queue

- **Status:** Accepted
- **Date:** 2026-03-24
- **Decision:**
  - Store experiments and job metadata in Postgres (with file fallback).
  - Route background refresh jobs through a Postgres queue consumed by a dedicated worker process.
- **Why now:**
  - In-memory/background tasks inside API process do not survive restarts.
  - API latency should stay predictable while long jobs run independently.
  - This gives production-lite reliability without immediate Kubernetes migration.
- **Implementation notes:**
  - `EXPERIMENT_STORE_BACKEND=postgres`
  - `JOB_STORE_BACKEND=postgres`
  - `JOB_QUEUE_BACKEND=postgres`
  - `docker-compose` includes a separate `worker` service running `scripts/job_worker.py`.

## Migration Triggers (when to move beyond filesystem-only)

Consider introducing stronger data infrastructure (Postgres metadata tables, object storage, warehouse, or orchestrator) when one or more triggers are true:

1. Universe scales to hundreds/thousands of tickers with frequent refresh.
2. Multiple backend instances write data concurrently.
3. Need strong audit/versioning for features and training sets.
4. Need low-latency ad-hoc slicing/filtering across many assets.
5. Team requires job orchestration, retries, and lineage visibility.

## 30 / 60 / 90 Day Roadmap

### 30 days

- Add batch downloader for ticker universe with resume/retry.
- Auto-run ETL after successful raw refresh.
- Enable pre-commit locally for all contributors.
- Keep `uv.lock` and dependency hygiene stable.

### 60 days

- Add worker heartbeat and dead-job requeue policy.
- Add structured logs and basic metrics (success/fail/latency).
- Introduce feature schema checks before model training.

### 90 days

- Decide storage upgrade path:
  - Keep Parquet + add metadata DB, or
  - Introduce warehouse/feature-store component.
- Add scheduler/orchestrator for production refresh cadence.
- Formalize SLOs for freshness and prediction latency.
