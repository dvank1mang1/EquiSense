from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.schemas.backtest import BacktestMetrics, BacktestResponse, EquityPoint


def _backtest_root() -> Path:
    root = Path(settings.model_dir).resolve().parent / "jobs" / "backtests"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _result_path(run_id: str) -> Path:
    return _backtest_root() / f"{run_id}.json"


@dataclass
class BacktestResultRecord:
    run_id: str
    ticker: str
    model: str
    start_date: date
    end_date: date
    initial_capital: float
    metrics: dict[str, Any]
    equity_curve: list[dict[str, Any]]


class BacktestStore:
    def result_path(self, run_id: str) -> Path:
        return _result_path(run_id)

    def save(self, run_id: str, resp: BacktestResponse) -> Path:
        record = BacktestResultRecord(
            run_id=run_id,
            ticker=resp.ticker,
            model=resp.model,
            start_date=resp.start_date,
            end_date=resp.end_date,
            initial_capital=resp.initial_capital,
            metrics={
                "cumulative_return": resp.metrics.cumulative_return,
                "annualized_return": resp.metrics.annualized_return,
                "sharpe_ratio": resp.metrics.sharpe_ratio,
                "max_drawdown": resp.metrics.max_drawdown,
                "win_rate": resp.metrics.win_rate,
                "total_trades": resp.metrics.total_trades,
            },
            equity_curve=[
                {
                    "date": p.date.isoformat(),
                    "equity": p.equity,
                    "return_pct": p.return_pct,
                    "benchmark_equity": p.benchmark_equity,
                }
                for p in resp.equity_curve
            ],
        )
        path = self.result_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = asdict(record)
        blob["start_date"] = record.start_date.isoformat()
        blob["end_date"] = record.end_date.isoformat()
        blob["model"] = str(record.model)
        path.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, run_id: str) -> BacktestResponse | None:
        path = self.result_path(run_id)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        metrics = BacktestMetrics(**raw["metrics"])
        curve = [
            EquityPoint(
                date=date.fromisoformat(p["date"]),
                equity=float(p["equity"]),
                return_pct=float(p["return_pct"]),
                benchmark_equity=float(p.get("benchmark_equity"))
                if p.get("benchmark_equity") is not None
                else None,
            )
            for p in raw["equity_curve"]
        ]
        return BacktestResponse(
            ticker=str(raw["ticker"]),
            model=str(raw["model"]),
            start_date=date.fromisoformat(str(raw["start_date"])),
            end_date=date.fromisoformat(str(raw["end_date"])),
            initial_capital=float(raw["initial_capital"]),
            metrics=metrics,
            equity_curve=curve,
        )
