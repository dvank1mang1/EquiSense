#!/usr/bin/env bash
# One-shot laptop demo: fetch multi-year OHLCV, ETL, train flat artifacts for UI.
# Requires: uv (https://docs.astral.sh/uv/), network for yfinance.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export EQUISENSE_DATA_ROOT="${EQUISENSE_DATA_ROOT:-$ROOT/data}"
export MODEL_DIR="${MODEL_DIR:-$ROOT/data/models}"

echo "==> EquiSense demo (repo root: $ROOT)"
echo "    DATA -> $EQUISENSE_DATA_ROOT"
echo "    MODEL_DIR -> $MODEL_DIR"

cd "$ROOT/backend"
uv sync --all-groups

TICKERS=(AAPL MSFT GOOGL TSLA AMZN NVDA META JPM)
echo "==> Download OHLCV 2021-01-01 .. 2025-12-31 (yfinance end exclusive -> 2026-01-01)"
uv run python scripts/download_ohlcv_dataset.py yfinance \
  --tickers "${TICKERS[@]}" \
  --start-date 2021-01-01 \
  --end-date 2026-01-01 \
  --sleep 0.35 \
  --run-etl

echo "==> Coverage summary"
uv run python scripts/print_ohlcv_coverage.py --data-root "$EQUISENSE_DATA_ROOT"

DEMO_TICKER="${DEMO_TICKER:-AAPL}"
echo "==> Train flat joblibs + metrics sidecars on $DEMO_TICKER"
uv run python scripts/train_flat_demo_model.py --ticker "$DEMO_TICKER" --all \
  --min-rows 35 --calibration-min-val 10

echo ""
echo "Done. Next:"
echo "  docker compose up --build   # from $ROOT"
echo "  or API only:  cd $ROOT/backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo "  frontend:     cd $ROOT/frontend && npm install && npm run dev"
