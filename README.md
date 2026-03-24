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

### 1. Клонировать и настроить окружение

```bash
git clone <repo-url>
cd EquiSense
cp .env.example .env
# Заполнить API ключи в .env
```

### 2. Запустить через Docker

```bash
docker-compose up --build
```

Сервисы будут доступны:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 3. Локальная разработка (без Docker)

**Backend** ([uv](https://docs.astral.sh/uv/) — один lockfile, быстрый venv):

```bash
cd backend
# при необходимости: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --all-groups   # runtime + dev (pytest)
uv run uvicorn main:app --reload
# тесты: uv run pytest
# quality: uv run ruff check . && uv run mypy app
```

Без dev-зависимостей: `uv sync`. Lockfile: `backend/uv.lock` (коммитить в git).

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
| ML Models | `backend/app/models/` | LR, RF, XGBoost, LightGBM, FinBERT |
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
   - Separate `api` and background worker process (jobs/training).
   - Keep Postgres for control-plane metadata (jobs/experiments/model registry).
   - Add regular backup policy for Postgres volume.

2. **Add operational guardrails**
   - Health/readiness probes (`/health` + dependency checks).
   - Structured logs with request and run identifiers.
   - Alerting from `SLO.md` thresholds (freshness, latency, failure rate).

3. **Introduce queue only when needed**
   - Add Redis + task queue if job concurrency becomes a bottleneck.
   - Move long-running training/backtesting to workers.
   - Keep API latency predictable under load.

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
