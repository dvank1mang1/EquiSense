# EquiSense — отчёт о состоянии проекта

Краткий снимок для того, кто подключается к репозиторию: что уже есть, как запускать Python-часть через **uv**, что недавно менялось и куда логично двигаться дальше.

---

## Зачем этот файл

Чтобы за 5–10 минут понять: стек, где лежит backend, как поднять окружение без «магии pip», и какие куски пайплайна уже собраны vs в планах.

---

## Переход на uv (Python / backend)

**uv** — менеджер окружений и зависимостей от Astral (аналог быстрого `pip + venv`, с lockfile). Для EquiSense backend это основной способ работы с зависимостями.

| Что | Где |
|-----|-----|
| Манифест зависимостей | `backend/pyproject.toml` |
| Зафиксированные версии (коммитить в git) | `backend/uv.lock` |
| Версия Python | `backend/.python-version` → **3.11** |
| Dev-зависимости (pytest и т.д.) | группа `[dependency-groups] dev` |

Типовые команды (из каталога `backend/`):

```bash
uv sync                 # только runtime
uv sync --all-groups    # + dev (pytest)
uv run pytest tests -q  # тесты (как в CI)
uv run ruff check app tests && uv run ruff format --check app tests && uv run mypy app/domain app/contracts app/services app/data
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

В корневом `README.md` уже описан быстрый старт с Docker и локальный вариант с **uv**. Важно: в `pyproject.toml` стоит `package = false`, поэтому проект не ставится как pip-пакет; `pytest` подхватывает код через `pythonpath = ["."]` в `[tool.pytest.ini_options]`.

---

## Что уже сделано (архитектура и код)

### Общая картина

- **Backend:** FastAPI в `backend/`, доменные типы в `app/domain/`, контракты (протоколы) в `app/contracts/`.
- **Данные:** адаптеры Alpha Vantage (OHLCV, quote, OVERVIEW), новости (Finnhub / NewsAPI), кэш на диске: Parquet для OHLCV, JSON для фундаментала и котировок.
- **Фичи:** technical / fundamental engineering, **sentiment (FinBERT)** → `FeatureStore` (Parquet под `data/processed/…`).
- **ML:** несколько моделей, сервис предсказаний с тяжёлым кодом в `asyncio.to_thread`, readiness/ensure-ready/status контур для тикера, backtesting API; champion-артефакты по `run_id`, lifecycle store (memory/postgres).
- **Тесты:** unit + integration; локально/CI: `uv run pytest tests -q` (см. актуальный счётчик в CI / после `pytest`).

### Недавние доработки слоя данных

- **Общий rate limiter** для Alpha Vantage (интервал по умолчанию ~12 с, настраивается через `alpha_vantage_min_interval_sec` в настройках).
- **TTL-кэш:** свежесть full OHLCV Parquet, JSON фундаментала, JSON котировки — отдельные таймауты в конфиге.
- **Инкрементальное обновление OHLCV:** подтягивание `compact` и **merge** с уже сохранённым full-рядом (`merge_ohlcv_history`); при пустом кэше или `force_full` — полная выгрузка.
- **API:** `POST /stocks/{ticker}/refresh` — тело с флагами `ohlcv`, `force_full`, `fundamentals`, `quote`, **`news`** (кэш в `data/raw/news/{TICKER}.json`, без FinBERT в HTTP).
- **Скрипт проверки:** `backend/scripts/verify_data_pull.py` — смоук с реальным ключом `ALPHA_VANTAGE_API_KEY` (см. `--help` / `--full`).
- **Зависимости:** `pandas-ta` убран (несовместимость с текущей версией Python в проекте); **LightGBM** поднят до версии с готовыми колёсами на Apple Silicon.

### Усиление engineering-практик (последние изменения)

- **Quality gates:** добавлены `ruff`, `mypy`, `pre-commit`, CI workflow (`.github/workflows/backend-ci.yml`).
- **Типизация:** расширен mypy coverage на `app/domain`, `app/contracts`, `app/services`, `app/data` (+ `app/jobs` / `app/api/jobs.py` в локальной проверке).
- **Pydantic warnings:** конфликт `model_*` namespace закрыт через `model_config` в настройках и схемах.
- **Оркестрация batch:** добавлены `backend/app/jobs/batch_refresh.py` и `backend/app/jobs/registry.py`.
- **Jobs API:** новые endpoint-ы под запуск и мониторинг refresh (`/api/v1/jobs/refresh-universe...`).
- **Lineage + metrics:** по run пишутся `status`, `lineage` и `metrics` артефакты в локальный jobs-каталог.
- **Data contracts:** добавлен модуль валидации схем `backend/app/data/validation.py`; проверки подключены в ETL/feature storage.
- **SLO/SLI:** добавлен `SLO.md` (freshness/latency/error budget + базовые alert-триггеры).

### Что добавили после этого (актуальный changelog)

- **Prediction readiness контур:** `GET /api/v1/predictions/{ticker}/readiness` + `POST /ensure-ready` + `GET /status`.
- **Backtesting API:** `run` + `compare` вынесены на сервисный слой, добавлены строгие Pydantic-схемы и OpenAPI примеры.
- **Единый error contract:** глобальные обработчики ошибок и `ErrorResponse` + `X-Request-ID` в ответах.
- **Training lifecycle:** запуск и трекинг `POST /api/v1/models/{model_id}/train` и `GET /train/{run_id}`.
- **Реальный training pipeline:** теперь run не просто валидирует вход, а делает `fit/evaluate/save` модели на `combined` фичах с метриками (`f1`, `roc_auc`, `precision`, `recall`) в статусе run.
- **Experiment Registry (v1):** добавлены endpoint-ы `GET /api/v1/models/{model_id}/experiments` и `GET /experiments/{run_id}`; у run теперь есть `params` и `dataset_fingerprint` для воспроизводимости.
- **Experiment persistence backend:** добавлен `ExperimentStore` с режимами `memory` (default) и `postgres` через `EXPERIMENT_STORE_BACKEND=postgres`; Postgres-режим пишет в таблицу `training_experiments` с graceful fallback.
- **Docker + Postgres runtime fix:** исправлен `docker-compose` для backend с bind-mount (добавлен отдельный volume `backend_venv:/app/.venv`), backend стабильно поднимается вместе с Postgres.
- **E2E smoke в контейнерах:** проверены `/health`, запуск `POST /api/v1/models/{model_id}/train` и факт сохранения run в Postgres-таблицу `training_experiments`.
- **Job persistence backend:** `JobStore` расширен Postgres-реализацией (`job_runs`, `job_lineage`) с переключателем `JOB_STORE_BACKEND` и fallback на file-store.
- **Async-safety для storage IO:** операции чтения/записи `JobStore` в batch/jobs/predictions переведены в `asyncio.to_thread`, чтобы sync storage-слой не блокировал event loop.
- **API/Worker split (runtime):** `refresh-universe` в background-режиме теперь кладёт задачу в Postgres-очередь (`job_queue`), отдельный worker (`scripts/job_worker.py`) забирает и выполняет run.
- **Docker compose:** добавлен сервис `worker`; для backend/worker заведён `JOB_QUEUE_BACKEND=postgres`.
- **Champion → артефакт inference:** обучение пишет run-scoped `model.joblib`, promote задаёт champion; predictions с селектором `champion` / `champion:model_a` грузят именно этот артефакт.
- **Lifecycle persistence:** `LIFECYCLE_STORE_BACKEND=postgres` + таблицы `model_lifecycle` / `model_lifecycle_history` (с resilient fallback).
- **FinBERT sentiment ETL:** `raw/news/{TICKER}.json` → `SentimentFeatureEngineer` (lazy load, `FINBERT_DEVICE` auto/cpu/cuda) → `processed/.../sentiment.parquet`; batch refresh при `run_etl` всегда вызывает `run_sentiment`; флаг **`refresh_news`** подтягивает новости перед ETL. Скрипт: `scripts/refresh_universe.py --run-etl --refresh-news`.
- **Nightly data warmup (GitHub Actions):** добавлен workflow `.github/workflows/nightly-refresh-universe.yml`, который ежедневно в `01:30 UTC` ставит `refresh-universe` job (`run_etl=true`, `refresh_news=true`) и ждёт завершения через polling status endpoint.
- **Model Ops automation (GitHub Actions):** добавлен workflow `.github/workflows/nightly-model-retrain.yml`, который ежедневно в `03:00 UTC` запускает train для `model_a..model_f`, ждёт terminal status и вызывает promotion endpoint с policy-gate.
- **Promotion policy gate:** manual/auto promote теперь возвращает прозрачное `promotion_decision` (accepted/reason/checks). Решение пишется в `metrics.promotion_decision` run-а, а при accepted обновляется lifecycle champion.
- **Ops summary endpoint:** `GET /api/v1/models/nightly/summary` показывает latest run/champion/promotion decision по rollout-моделям.
- **Research stack hardening (ML):**
  - Добавлен **CPCV (Combinatorial Purged CV)** в `backend/app/ml/cv.py`: `combinatorial_purged_cv_splits(...)` с purge-окном `gap = label_horizon_days + embargo_days`, ограничением `max_splits` и seed-based sampling комбинаций.
  - Добавлены **OOF primary probabilities** для meta-labeling в `backend/app/ml/oof.py`: `oof_primary_proba(...)`; в research pack meta-модель учится на OOF-скоринге primary-модели (с fallback на val при недостатке строк).
  - Добавлен **SPA-lite** в `backend/app/ml/spa_lite.py`: `block_bootstrap_mean_pvalue(...)` (circular block bootstrap для p-value по среднему excess-return относительно benchmark).
  - `notebooks/run_research_pack.py` расширен CLI-параметрами `--cpcv-groups`, `--cpcv-max-splits`, `--spa-bootstrap`; результаты сохраняются в `cv_fold_metrics.csv` (`split_name=cpcv`), `cv_summary.csv` (`cpcv_mean_auc`, `cpcv_std_auc`), `spa_lite_holdout.csv` и поля `spa_*` в `backtest_stats.csv`.
  - Для ML-модулей добавлены/обновлены unit-тесты в `backend/tests/unit/test_ml_finance.py` (CPCV и SPA-lite), локально: `10 passed`.

### Production training (API) — `TrainingService` + `app/ml/training_pipeline.py`

Обучение по `POST /api/v1/models/{model_id}/train` для тикера:

| Этап | Что делается |
|------|----------------|
| **Данные** | `FeatureStore.build_combined(ticker)` → таргет: знак **следующего** дневного `returns` (согласовано с `returns` = `close.pct_change()` в technical). |
| **Сплит** | Хронологический по долям времени (`TRAINING_SPLIT_TRAIN_FRACTION`, `TRAINING_SPLIT_VAL_END_FRACTION`, по умолчанию ~70/15/15); `TRAINING_MIN_ROWS` — минимум строк; дубликаты `date` схлопываются. |
| **Препроцессинг** | `SimpleImputer(median)` на train в `Pipeline` до модели; баланс классов для деревьев/бустингов (`scale_pos_weight` / `class_weight`). |
| **Калибровка** | На **validation**: `CalibratedClassifierCV(..., cv="prefit", method="isotonic")`; порог размера val — `TRAINING_CALIBRATION_MIN_VAL_SAMPLES`. В metrics: `calibration` (код, напр. `isotonic_applied`, `skipped_val_lt_50`) и `calibration_isotonic`. Ошибки fit логируются и дают `skipped_calibrator_fit_error`. |
| **Логи** | Успех: `loguru` info с `roc_auc` и статусом калибровки; падение: `logger.exception` со stack trace. |
| **Оценка** | Метрики на **test**: `f1`, `roc_auc`, `pr_auc`, `brier`, precision, recall + строки и даты по сплитам. |
| **Артефакт** | `model.joblib` под run (imputer + при необходимости калибратор). |

**Исследования (офлайн):** `notebooks/run_research_pack.py` → `notebooks/results/`; оглавление файлов: `notebooks/RESEARCH_OUTPUTS.md`; итоговый текст: `RESEARCH_SUMMARY.md`; ссылки на статьи: `notebooks/LITERATURE_REVIEW.md`.

---

## Как быстро проверить, что данные реально тянутся

1. Положить `ALPHA_VANTAGE_API_KEY` в `backend/.env` (или в окружение).
2. Выполнить из `backend/`:

   ```bash
   uv run python scripts/verify_data_pull.py AAPL
   ```

   Для трёх вызовов подряд (медленнее из-за лимита):

   ```bash
   uv run python scripts/verify_data_pull.py AAPL --full
   ```

3. Либо поднять API и вызвать `POST /stocks/{ticker}/refresh` (см. Swagger `/docs`).

---

## Nightly warmup: что выставить в GitHub

Пока сервер может быть не поднят, ниже фиксируем значения для Actions заранее.

### Secrets

1. `NIGHTLY_REFRESH_API_BASE_URL` (**обязательно**)
   - Базовый URL backend, без `/api/v1` в конце.
   - Примеры:
     - `https://api.equisense.yourdomain.com`
     - `http://<server-ip>:8000`

2. `NIGHTLY_REFRESH_BEARER_TOKEN` (**опционально**)
   - Нужен, если API закрыт Bearer auth.
   - Значение: сам токен строкой (без префикса `Bearer `).

### Variables

1. `NIGHTLY_TICKERS` (**рекомендуется**)
   - Список тикеров через запятую, без кавычек.
   - Пример:
     - `AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,AVGO,AMD,TSM`

Если `NIGHTLY_TICKERS` не задан, workflow использует дефолтный набор:
`AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA`.

---

## Дальнейшие шаги (рекомендации)

Ниже — практичный бэклог; часть пересекается с `Plan.md`, но сформулирована как «что делать следующим».

1. **Worker / ops** — расширить метрики (в т.ч. длительность FinBERT-шага), алерты по `SLO.md`.
2. **Alerting runtime** — подключить отправку алертов по правилам из `SLO.md` (Telegram/Slack/webhook).
3. **Training / registry** — расширить версионирование промптов/пайплайна sentiment при смене модели FinBERT.
4. **Frontend** — экран jobs/training monitor: запуск, прогресс, причины fail, lineage/metrics.
5. **Backtesting → product loop** — связать результаты backtest с UX выбора модели и автоподсказками по retrain.
6. **Расширение mypy coverage** — постепенно подключить `app/models` и `app/explainability` после локального рефакторинга.

---

## Где смотреть подробности

| Документ / путь | Содержание |
|-----------------|------------|
| `README.md` | Стек, структура, Docker, uv, фронт |
| `Plan.md` | Продуктовое ТЗ и видение фич |
| `SLO.md` | Целевые SLI/SLO и error budget |
| `ARCHITECTURE_DECISIONS.md` | ADR, триггеры миграции, roadmap 30/60/90 |
| `backend/app/data/` | Рынок, фундаментал, merge, rate limit |
| `backend/app/features/sentiment.py` | FinBERT → daily sentiment Parquet |
| `backend/app/jobs/` | Оркестрация batch refresh, lineage, metrics |
| `backend/app/api/stocks.py` | Эндпоинты акций и ticker-refresh |
| `backend/app/api/jobs.py` | Запуск/статус/lineage/metrics batch job-ов |

---

*Документ снимок на момент последних правок; при крупных изменениях в репозитории имеет смысл обновить раздел «Что уже сделано».*
