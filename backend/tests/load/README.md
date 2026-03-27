# Load tests (k6)

Набор нагрузочных сценариев для API/queue. Эти тесты не требуют изменения Python-кода и запускаются отдельно.

## Prerequisites

- поднят backend (`http://localhost:8000` по умолчанию)
- установлено `k6`

Пример установки на macOS:

```bash
brew install k6
```

## Быстрый запуск

Из корня репозитория:

```bash
k6 run backend/tests/load/k6_api_smoke.js
k6 run backend/tests/load/k6_backtesting.js
k6 run backend/tests/load/k6_jobs_queue.js
```

## Сценарии

- `k6_api_smoke.js`
  - `/api/v1/stocks/{ticker}/history`
  - `/api/v1/predictions/{ticker}`
  - `/api/v1/predictions/{ticker}/compare`

- `k6_backtesting.js`
  - `/api/v1/backtesting/{ticker}`
  - `/api/v1/backtesting/{ticker}/compare`

- `k6_jobs_queue.js`
  - enqueue: `POST /api/v1/jobs/refresh-universe`
  - poll status: `GET /api/v1/jobs/refresh-universe/{run_id}`
  - worker metrics: `GET /api/v1/jobs/worker/metrics`

## Полезные env-переменные

```bash
BASE_URL=http://localhost:8000
TICKER=AAPL
```

Для `k6_backtesting.js`:

```bash
START_DATE=2024-01-01
END_DATE=2024-12-31
INITIAL_CAPITAL=10000
```

Для `k6_jobs_queue.js`:

```bash
TICKERS=AAPL,MSFT,NVDA
RUN_ETL=false
REFRESH_NEWS=false
```

## Примеры

```bash
BASE_URL=http://localhost:8000 TICKER=MSFT k6 run backend/tests/load/k6_api_smoke.js

BASE_URL=http://localhost:8000 TICKER=AAPL START_DATE=2023-01-01 END_DATE=2024-12-31 \
k6 run backend/tests/load/k6_backtesting.js

BASE_URL=http://localhost:8000 TICKERS=AAPL,MSFT RUN_ETL=false REFRESH_NEWS=false \
k6 run backend/tests/load/k6_jobs_queue.js
```

## Как читать результаты

- `http_req_failed` должен быть низким (в thresholds задан допустимый порог).
- `p(95)` по `http_req_duration` не должен превышать пороги сценария.
- Для backtesting допустимы более высокие latency, чем для обычных read-endpoint-ов.
