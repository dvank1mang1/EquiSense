# EquiSense

Публичное демо: **https://grimy-paradox-salute.ngrok-free.dev** (ngrok, URL может смениться).

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

### Локальный «одним скриптом» (laptop demo)

Из корня репозитория (нужны `uv` и сеть для Yahoo/Stooq/AV по цепочке `auto`):

```bash
./scripts/demo_local.sh
```

Скрипт кладёт OHLCV в `./data` с окном **2021-01-01 … 2025-12-31** (`yfinance` с `--end-date 2026-01-01`, конец **исключающий**), прогоняет ETL и пишет плоские модели в `./data/models`. Источники и ограничения: `DATA_SOURCES.md`.

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

После первого старта, чтобы **бэктест и прогнозы** видели фичи, один раз прогоните данные и ETL в общий volume `./data` (из хоста, пока контейнеры запущены):

```bash
docker compose exec backend uv run python scripts/download_ohlcv_dataset.py public-sample --run-etl
docker compose exec backend uv run python scripts/train_flat_demo_model.py --ticker AAPL --all
```

Флаг **`--all`** обучает **baseline_lr** и **model_a … model_f** (все переключатели в UI) и пишет плоские `*.joblib` в `data/models/`. Одна модель: `--model model_d` без `--all`. Свой набор OHLCV — см. раздел «Локальные котировки» ниже.

Сервисы будут доступны:
- Frontend: http://localhost:3002
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

### Локальные котировки и ETL без Alpha Vantage

Если в UI «нет данных» по тикеру, чаще всего нет файла `data/raw/ohlcv/{TICKER}.parquet`. Лимиты Alpha Vantage обходятся так: подтянуть OHLCV через **yfinance** и прогнать тот же ETL, что и для raw (technical / fundamental / sentiment с нулевыми новостями).

Из каталога `backend/`:

```bash
uv run python scripts/download_ohlcv_dataset.py yfinance \
  --tickers AAPL MSFT GOOGL TSLA AMZN NVDA META JPM \
  --period 10y --sleep 0.25 --run-etl
```

Подкоманда `yfinance` по умолчанию использует **`--source auto`**: сначала Yahoo (`download` + `history`), при пустом ответе или ошибке JSON — **Stooq**. У Stooq для выдачи CSV нужен ключ: страница [get_apikey](https://stooq.com/q/d/?s=aapl.us&get_apikey) → `export STOOQ_API_KEY=...`. Только Stooq: `--source stooq`.

- По умолчанию данные пишутся в **`EquiSense/data/`** (корень репозитория), совпадает с volume `./data:/app/data` в `docker-compose`.
- Другой каталог: переменная `EQUISENSE_DATA_ROOT=/path/to/data` или флаг **`--data-root` только перед подкомандой**:  
  `uv run python scripts/download_ohlcv_dataset.py --data-root /abs/path/data yfinance --tickers AAPL --run-etl`
- Локальный `uvicorn` из `backend/` по умолчанию смотрит в `backend/data/`. Чтобы использовать общий каталог с Docker, задайте, например:  
  `export MODEL_DIR="$(cd .. && pwd)/data/models"` перед запуском API.

Быстро без ключей и без Yahoo/Stooq: **`public-sample`** — один CSV с jsDelivr (Vega Datasets), несколько тикеров (месячные цены как синтетический OHLCV для демо):

```bash
uv run python scripts/download_ohlcv_dataset.py public-sample --run-etl
```

Ещё: `plotly-demo` (только AAPL), `stooq` (+`STOOQ_API_KEY`), импорт `csv` — см. `backend/scripts/download_ohlcv_dataset.py --help`.

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

## Операционный план (docker-compose)

Сейчас: `docker-compose` + Postgres + FastAPI и отдельный worker для джоб.

1. Стабильный compose, бэкапы Postgres, health/readiness и нормальные логи.
2. Очередь: Postgres + `scripts/job_worker.py`; отдельный Redis — только если упираетесь в конкуренцию задач.

Переменные окружения (см. `.env.example`):

- `EXPERIMENT_STORE_BACKEND=postgres` — реестр экспериментов.
- `JOB_STORE_BACKEND=postgres` — статусы джоб.
- `JOB_QUEUE_BACKEND=postgres` — очередь API → worker.
- `LIFECYCLE_STORE_BACKEND=postgres` — champion-модели после рестартов.
- `FINBERT_DEVICE=auto|cpu|cuda`, `FINBERT_BATCH_SIZE`, `FINBERT_MODEL_NAME` — sentiment ETL.

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

## Исследовательский слой (опционально)

Код в `backend/app/research_models/` — отдельный CLI, не влияет на прод-пайплайн.

Примеры (из `backend/`):

```bash
# 1) Baseline classification + top-k execution
uv run python scripts/run_research_experiment.py \
  --research_mode \
  --tickers AAPL MSFT NVDA AMZN \
  --model_type classification \
  --strategy_type top_k \
  --top_k_pct 0.2 \
  --rebalance_every weekly \
  --score_normalization

# 2) Regression model aligned to fwd_5d + hold_5d execution
uv run python scripts/run_research_experiment.py \
  --research_mode \
  --tickers AAPL MSFT NVDA AMZN \
  --model_type regression \
  --strategy_type hold_5d \
  --top_k_pct 0.2 \
  --hold_days 5

# 3) Compare classification/regression/ranking in one command
uv run python scripts/run_research_experiment.py \
  --research_mode \
  --tickers AAPL MSFT NVDA AMZN \
  --strategy_type top_k \
  --top_k_pct 0.2 \
  --compare_all
```

Артефакты пишутся в `backend/research_outputs/<run>/` (каталог в `.gitignore`): `summary.json`, `predictions.csv`, `strategy_daily.csv`, `decile_table.csv`, `regime_ic.csv`, `decile_mean_fwd5d.png` и др.

## Disclaimer

Проект разработан в образовательных целях. Не является торговым советником и не гарантирует прибыль.
