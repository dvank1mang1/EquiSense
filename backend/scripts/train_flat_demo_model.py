"""Обучить модель(и) и положить плоские артефакты ``{MODEL_DIR}/{model_id}.joblib`` для inference.

API и UI ожидают именно эти файлы (или champion-run), иначе GET /predictions возвращает 404.
Рядом пишется ``{{model_id}}.metrics.json`` (F1/ROC для таблицы сравнения моделей), т.к. experiment store по умолчанию in-memory.

Примеры:

  cd backend
  uv run python scripts/train_flat_demo_model.py --ticker AAPL --model model_d

  # Все модели из селектора UI: baseline_lr + model_a … model_f
  uv run python scripts/train_flat_demo_model.py --ticker AAPL --all

  docker compose exec backend uv run python scripts/train_flat_demo_model.py --ticker AAPL --all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="AAPL", help="Тикер с уже готовым combined (после ETL)")
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--model",
        default="model_d",
        help="Одна модель: baseline_lr, model_a … model_f, model_g_ranker",
    )
    g.add_argument(
        "--all",
        action="store_true",
        help="Обучить baseline_lr + model_a … model_f (как в выпадающем списке прогноза)",
    )
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help="При --all не останавливаться на первой ошибке (печать и дальше)",
    )
    p.add_argument(
        "--min-rows",
        type=int,
        default=35,
        help="TRAINING_MIN_ROWS (≥30; для демо-данных часто 35–40)",
    )
    p.add_argument(
        "--calibration-min-val",
        type=int,
        default=10,
        help="TRAINING_CALIBRATION_MIN_VAL_SAMPLES (меньше — чаще skip isotonic на коротком val)",
    )
    return p.parse_args()


async def _wait_done(svc, run_id: str):
    while True:
        r = await svc.get_status(run_id)
        if r is None:
            raise RuntimeError(f"run {run_id} not found")
        if r.status == "completed":
            return r
        if r.status == "failed":
            raise RuntimeError(r.error or "training failed")
        await asyncio.sleep(0.3)


def _metric_float(m: dict | None, key: str) -> float | None:
    if not m:
        return None
    raw = m.get(key)
    if raw is None:
        return None
    try:
        out = float(raw)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


async def _train_one_flat(svc, sym: str, mid) -> Path:
    from app.core.config import get_settings

    print(f"training {mid.value} on {sym} …")
    run = await svc.start_training(mid, sym)
    print("  run_id:", run.run_id)
    done = await _wait_done(svc, run.run_id)
    if not done.artifact_path:
        raise RuntimeError("completed run has no artifact_path")

    settings = get_settings()
    flat = Path(settings.model_dir).resolve() / f"{mid.value}.joblib"
    flat.parent.mkdir(parents=True, exist_ok=True)
    src = Path(done.artifact_path)
    shutil.copy2(src, flat)
    meta = src.with_suffix(src.suffix + ".meta.json")
    if meta.is_file():
        shutil.copy2(meta, flat.with_suffix(flat.suffix + ".meta.json"))

    # Для UI (compare F1/ROC): при backend=memory store пуст после выхода скрипта — пишем рядом с joblib.
    metrics_path = flat.parent / f"{mid.value}.metrics.json"
    if done.metrics:
        payload: dict[str, str | float] = {"ticker": sym}
        for key in ("f1", "roc_auc", "precision", "recall"):
            v = _metric_float(done.metrics, key)
            if v is not None:
                payload[key] = v
        metrics_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print("  wrote", metrics_path)

    print("  wrote", flat)
    return flat


async def _async_main(args: argparse.Namespace) -> None:
    from app.domain.identifiers import ROLLOUT_MODEL_IDS, ModelId
    from app.services.dependencies import get_training_service

    svc = get_training_service()
    sym = args.ticker.strip().upper()

    if args.all:
        models: tuple[ModelId, ...] = (ModelId.BASELINE_LR, *ROLLOUT_MODEL_IDS)
        errors: list[str] = []
        for mid in models:
            try:
                await _train_one_flat(svc, sym, mid)
            except Exception as e:  # noqa: BLE001
                msg = f"{mid.value}: {e}"
                errors.append(msg)
                print(f"  FAIL {msg}", file=sys.stderr)
                if not args.continue_on_error:
                    raise
        if errors and args.continue_on_error:
            print(f"\nГотово с ошибками ({len(errors)}/{len(models)}). Проверьте лог выше.")
        elif not errors:
            print(f"\nВсе {len(models)} моделей записаны в MODEL_DIR. Обновите UI.")
        return

    mid = ModelId(args.model)
    await _train_one_flat(svc, sym, mid)
    print("Перезагрузите страницу прогноза или повторите запрос.")


def main() -> None:
    args = _parse_args()
    os.environ["TRAINING_MIN_ROWS"] = str(max(30, args.min_rows))
    os.environ["TRAINING_CALIBRATION_MIN_VAL_SAMPLES"] = str(max(10, args.calibration_min_val))
    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
