import json
from pathlib import Path

import pandas as pd
import pytest

from app.core.config import settings
from app.jobs.batch_refresh import BatchRefreshOrchestrator


class _FakeMarket:
    async def refresh_ohlcv(self, ticker: str, *, force_full: bool = False) -> pd.DataFrame:
        _ = force_full
        return pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-03-24"),
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ]
        )

    async def get_current_price(self, ticker: str, *, skip_cache: bool = False) -> dict:
        _ = ticker, skip_cache
        return {"price": 123.45}


class _FakeFundamentals:
    async def get_snapshot(self, ticker: str, *, force: bool = False) -> dict:
        _ = force
        return {"Symbol": ticker.upper()}


class _FakeETL:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_technical(self, ticker: str):
        self.calls.append(f"tech:{ticker.upper()}")
        return Path("/tmp/tech.parquet")

    def run_fundamental(self, ticker: str):
        self.calls.append(f"fund:{ticker.upper()}")
        return Path("/tmp/fund.parquet")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orchestrator_writes_status_and_lineage(tmp_path: Path) -> None:
    old_model_dir = settings.model_dir
    settings.model_dir = str(tmp_path / "models")
    try:
        etl = _FakeETL()
        orchestrator = BatchRefreshOrchestrator(
            market=_FakeMarket(),
            fundamentals=_FakeFundamentals(),
            etl_runner=etl,
            retry_attempts=1,
            retry_wait_sec=0.01,
        )
        status_path, lineage_path = await orchestrator.run(["aapl", "msft"], run_etl=True)

        assert status_path.exists()
        assert lineage_path.exists()

        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["tickers_total"] == 2
        assert status["success"] == 2
        assert status["failed"] == 0

        lines = lineage_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        row0 = json.loads(lines[0])
        assert row0["status"] == "ok"
        assert row0["ohlcv_rows"] == 1
        assert row0["etl_status"] == "ok"
        assert etl.calls == ["tech:AAPL", "fund:AAPL", "tech:MSFT", "fund:MSFT"]
    finally:
        settings.model_dir = old_model_dir
