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
```

Без dev-зависимостей: `uv sync`. Lockfile: `backend/uv.lock` (коммитить в git).

С **docker-compose** и bind-mount `./backend:/app` контейнер видит твой локальный `backend/.venv` — перед `docker compose up` выполни в `backend/` хотя бы `uv sync` (или положи venv в репозиторий не нужно: `.venv` в `.gitignore`).

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

## Disclaimer

Проект разработан в образовательных целях. Не является торговым советником и не гарантирует прибыль.
