# EquiSense

ML-платформа для анализа и прогнозирования движения акций. Объединяет технический анализ, фундаментальные данные и NLP-анализ новостей (FinBERT) для генерации торговых сигналов с объяснением через SHAP и backtesting.

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy |
| ML | scikit-learn, XGBoost, LightGBM, SHAP |
| NLP | HuggingFace Transformers, FinBERT |
| Storage | PostgreSQL, Parquet |
| Frontend | Next.js 14, Tailwind CSS, Plotly |
| DevOps | Docker, docker-compose, uv (Python env) |

## Структура проекта

```
EquiSense/
├── backend/          # FastAPI приложение + все ML-модули
├── frontend/         # Next.js веб-интерфейс
├── data/             # raw данные, feature store, модели
├── notebooks/        # EDA и эксперименты
├── scripts/          # утилиты для обучения и сидирования данных
└── docker-compose.yml
```

## Быстрый старт

### 0. Windows: рекомендуется WSL2

Для **Docker Compose**, **GPU (CUDA через WSL)** и путей как в Linux удобнее держать репозиторий **внутри файловой системы WSL** (например `~/projects/EquiSense`), а не только на `C:` через `/mnt/c/`. IDE: **Remote – WSL**. Нативный Windows тоже возможен, но WSL2 обычно меньше сюрпризов с контейнерами и `uv`.

### 1. Клонировать и настроить окружение

```bash
git clone <repo-url>
cd EquiSense
cp .env.example .env
# Заполнить API ключи в .env (Alpha Vantage; для новостей — Finnhub и/или NewsAPI)
```

### 2. Запустить через Docker

```bash
docker-compose up --build
```

Сервисы будут доступны:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (default: admin/admin)
- Grafana dashboard (auto-provisioned): `EquiSense / EquiSense API Overview`

### 3. Локальная разработка (без Docker)

**Backend** ([uv](https://docs.astral.sh/uv/) — один lockfile, быстрый venv):

```bash
cd backend
# при необходимости: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --all-groups   # runtime + dev (pytest)
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Проверки как в CI (из каталога `backend/`):

```bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy app/domain app/contracts app/services app/data
uv run pytest tests -q
```

Без dev-зависимостей: `uv sync`. Lockfile: `backend/uv.lock` (коммитить в git).

Метрики backend (Prometheus format): `GET /metrics` (настраивается через `METRICS_PATH`).

С **docker-compose** backend использует отдельный volume `backend_venv:/app/.venv`, поэтому локальный `backend/.venv` не ломает контейнерный runtime.

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Модули

| Модуль | Путь | Описание |
|---|---|---|
| Data Ingestion | `backend/app/data/` | Alpha Vantage, Finnhub, News API |
| Feature Engineering | `backend/app/features/` | Technical, Fundamental, Sentiment |
| ML Models | `backend/app/models/` | XGBoost / LightGBM классификаторы по слайсам фич |
| NLP / Sentiment | `backend/app/features/sentiment.py` | FinBERT (ProsusAI/finbert), батч-инференс, без дообучения |
| Backtesting | `backend/app/backtesting/` | Sharpe, Drawdown, Win Rate |
| Explainability | `backend/app/explainability/` | SHAP, Feature Importance |
| API | `backend/app/api/` | REST endpoints, WebSocket |

## Engineering quality gates

- Pre-commit hooks: `pre-commit install` (from repo root)
- Backend CI: `.github/workflows/backend-ci.yml` (ruff + mypy + pytest)
- Architecture decisions and migration triggers: `ARCHITECTURE_DECISIONS.md`
- SLO/SLI baseline and error budget: `SLO.md`

## Production-lite roadmap (without Kubernetes)

Current runtime is intentionally simple: `docker-compose` + `postgres` + FastAPI backend.
This is enough for early and mid-stage development if reliability controls are explicit.

Recommended sequence:

1. **Stabilize current compose runtime**
   - Separate `api` and background worker process (jobs/training). ✅
   - Keep Postgres for control-plane metadata (jobs/experiments/model registry).
   - Add regular backup policy for Postgres volume.

2. **Add operational guardrails**
   - Health/readiness probes (`/health` + dependency checks).
   - Structured logs with request and run identifiers.
   - Alerting from `SLO.md` thresholds (freshness, latency, failure rate).

3. **Introduce queue only when needed**
   - Current baseline: Postgres-backed queue + dedicated worker (`scripts/job_worker.py`).
   - Add Redis + task queue if job concurrency becomes a bottleneck.
   - Move long-running training/backtesting to workers.
   - Keep API latency predictable under load.

Operational switches:

- `EXPERIMENT_STORE_BACKEND=postgres` enables persistent experiment registry.
- `JOB_STORE_BACKEND=postgres` enables Postgres-backed job status/lineage/metrics.
- `JOB_QUEUE_BACKEND=postgres` enables API-to-worker background queue.
- `LIFECYCLE_STORE_BACKEND=postgres` persists champion promotions across API restarts.
- `FINBERT_DEVICE=auto|cpu|cuda`, `FINBERT_BATCH_SIZE`, `FINBERT_MODEL_NAME` — настройки sentiment ETL (см. `.env.example`).

### Новости и sentiment (FinBERT)

- **Сырьё:** `data/raw/news/{TICKER}.json` (кэш из Finnhub/NewsAPI; каталог `data/raw/` в `.gitignore`).
- **Обработка:** при batch ETL после technical + fundamental выполняется **`run_sentiment`** → `data/processed/{TICKER}/sentiment.parquet` (при отсутствии новостей — нулевые признаки, модель FinBERT не грузится).
- **Обновить только кэш новостей (лёгкий HTTP):** `POST /api/v1/stocks/{ticker}/refresh` с телом `"news": true` (остальные флаги по необходимости).
- **Полный конвейер (данные + ETL + опционально свежие новости):** `POST /api/v1/jobs/refresh-universe` с `"run_etl": true` и при необходимости `"refresh_news": true` (перед sentiment подтянет новости в `raw/news`). В фоне с `JOB_QUEUE_BACKEND=postgres` работу выполняет **`worker`** (`scripts/job_worker.py`).
- **CLI:** из `backend/`:

  ```bash
  uv run python scripts/refresh_universe.py --tickers AAPL,MSFT --run-etl --refresh-news
  ```

На GPU (Linux/WSL2 с NVIDIA): задайте `FINBERT_DEVICE=cuda` или оставьте `auto`. Первый запуск скачает веса с Hugging Face.

**Без GPU:** `FINBERT_DEVICE=cpu` — медленнее, но для отладки ETL достаточно. Сводка локальных файлов (raw/processed, возраст кэша): `GET /api/v1/stocks/{ticker}/artifacts`.

Worker operations API:

- `GET /api/v1/jobs/worker/health` — queue snapshot + stale-running health.
- `GET /api/v1/jobs/worker/metrics` — derived queue indicators (`queue_depth`, `failure_rate`, `dead_letter`).
- `GET /api/v1/jobs/worker/dead-letter` — list dead-letter runs.
- `POST /api/v1/jobs/worker/dead-letter/{run_id}/requeue` — manual requeue for failed run.

Model Ops additions:

- `POST /api/v1/models/{model_id}/lifecycle/promote/{run_id}` now returns `promotion_decision`
  (accepted/reason/checks), with optional `force=true` override.
- `GET /api/v1/models/nightly/summary` — latest training + champion + promotion decision
  across rollout models.
- Nightly retrain workflow: `.github/workflows/nightly-model-retrain.yml`
  (train model_a..model_f, then policy-based promote).

### Nightly data warmup for backtesting

To keep backtesting fast and independent from Alpha Vantage runtime limits, this repo includes
scheduled workflow `.github/workflows/nightly-refresh-universe.yml`.

It runs daily (01:30 UTC) and enqueues:

- `POST /api/v1/jobs/refresh-universe`
- with `run_etl=true` and `refresh_news=true`
- then polls `GET /api/v1/jobs/refresh-universe/{run_id}` until completion.

Configure in GitHub repository settings:

- Secret `NIGHTLY_REFRESH_API_BASE_URL` (example: `https://api.example.com`)
- Optional secret `NIGHTLY_REFRESH_BEARER_TOKEN`
- Optional repo variable `NIGHTLY_TICKERS` (comma-separated tickers)

You can also trigger it manually via Actions `workflow_dispatch` with custom ticker list.

4. **Return to Kubernetes only by triggers**
   - Need horizontal scaling for API/workers.
   - Need controlled rolling deploys across multiple environments.
   - Need autoscaling and self-healing beyond compose limits.

## Backtesting API (ready)

- Single model backtest:
  - `GET /api/v1/backtesting/{ticker}?model=model_d&start_date=2024-01-01&end_date=2024-12-31&initial_capital=10000`
- Compare all models on the same period:
  - `GET /api/v1/backtesting/{ticker}/compare?start_date=2024-01-01&end_date=2024-12-31`

Quick local check:

```bash
cd backend
uv run uvicorn main:app --reload
# then open /docs and run backtesting endpoints
```

## Disclaimer

Проект разработан в образовательных целях. Не является торговым советником и не гарантирует прибыль.
