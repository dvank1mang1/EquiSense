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
uv run pytest tests     # тесты
uv run uvicorn main:app --reload   # API (если entrypoint так настроен у вас)
```

В корневом `README.md` уже описан быстрый старт с Docker и локальный вариант с **uv**. Важно: в `pyproject.toml` стоит `package = false`, поэтому проект не ставится как pip-пакет; `pytest` подхватывает код через `pythonpath = ["."]` в `[tool.pytest.ini_options]`.

---

## Что уже сделано (архитектура и код)

### Общая картина

- **Backend:** FastAPI в `backend/`, доменные типы в `app/domain/`, контракты (протоколы) в `app/contracts/`.
- **Данные:** адаптеры Alpha Vantage (OHLCV, quote, OVERVIEW), новости (Finnhub / NewsAPI), кэш на диске: Parquet для OHLCV, JSON для фундаментала и котировок.
- **Фичи:** technical / fundamental engineering, `FeatureStore` (Parquet под `data/processed/…`).
- **ML:** несколько моделей, сервис предсказаний с тяжёлым кодом в `asyncio.to_thread`, readiness/ensure-ready/status контур для тикера, backtesting API.
- **Тесты:** unit + integration; последний полный прогон — **32 passed**.

### Недавние доработки слоя данных

- **Общий rate limiter** для Alpha Vantage (интервал по умолчанию ~12 с, настраивается через `alpha_vantage_min_interval_sec` в настройках).
- **TTL-кэш:** свежесть full OHLCV Parquet, JSON фундаментала, JSON котировки — отдельные таймауты в конфиге.
- **Инкрементальное обновление OHLCV:** подтягивание `compact` и **merge** с уже сохранённым full-рядом (`merge_ohlcv_history`); при пустом кэше или `force_full` — полная выгрузка.
- **API:** `POST /stocks/{ticker}/refresh` — тело с флагами `ohlcv`, `force_full`, `fundamentals`, `quote`.
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

## Дальнейшие шаги (рекомендации)

Ниже — практичный бэклог; часть пересекается с `Plan.md`, но сформулирована как «что делать следующим».

1. **Worker hardening** — heartbeat/health endpoint для worker + безопасное завершение текущего job при shutdown.
2. **Alerting runtime** — подключить отправку алертов по правилам из `SLO.md` (Telegram/Slack/webhook).
3. **Training hardening** — добавить версионирование артефактов, хранение train-конфигурации и метрик в отдельном реестре.
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
| `backend/app/jobs/` | Оркестрация batch refresh, lineage, metrics |
| `backend/app/api/stocks.py` | Эндпоинты акций и ticker-refresh |
| `backend/app/api/jobs.py` | Запуск/статус/lineage/metrics batch job-ов |

---

*Документ снимок на момент последних правок; при крупных изменениях в репозитории имеет смысл обновить раздел «Что уже сделано».*
