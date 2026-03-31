from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtesting.engine import BacktestEngine
from app.contracts.data_providers import MarketDataProvider
from app.contracts.features import FeatureStorePort
from app.core.config import settings
from app.data.persistence import read_ohlcv_parquet
from app.data.utils import normalize_ticker
from app.domain.exceptions import BacktestDependencyError, BacktestInputError
from app.domain.identifiers import ROLLOUT_MODEL_IDS, ModelId
from app.models import get_model_class
from app.schemas.backtest import BacktestMetrics, BacktestResponse, EquityPoint


@dataclass(frozen=True)
class BacktestCompareRow:
    model: str
    ok: bool
    metrics: dict[str, float | int] | None = None
    error: str | None = None


class BacktestingService:
    def __init__(
        self,
        market: MarketDataProvider,
        features: FeatureStorePort,
    ) -> None:
        self._market = market
        self._features = features

    async def preflight(self, ticker: str) -> dict[str, bool | str]:
        sym = ticker.strip().upper()
        sym_key = normalize_ticker(ticker)

        cached_ohlcv = await read_ohlcv_parquet(sym_key)
        has_cached_ohlcv = cached_ohlcv is not None and not cached_ohlcv.empty
        has_combined = self._features.exists(sym, "combined")

        ready = has_cached_ohlcv and has_combined
        reason = ""
        if not has_cached_ohlcv and not has_combined:
            reason = "missing cached OHLCV and combined features"
        elif not has_cached_ohlcv:
            reason = "missing cached OHLCV"
        elif not has_combined:
            reason = "missing combined features"

        return {
            "ticker": sym,
            "ready": ready,
            "has_cached_ohlcv": has_cached_ohlcv,
            "has_combined_features": has_combined,
            "reason": reason,
        }

    async def run_single(
        self,
        *,
        ticker: str,
        model: ModelId,
        start_date: date | None,
        end_date: date | None,
        initial_capital: float,
    ) -> BacktestResponse:
        sym = ticker.strip().upper()
        sym_key = normalize_ticker(ticker)
        # Local OHLCV first (see GET /stocks/{ticker}/history) — avoids Alpha Vantage per model on /compare.
        cached_ohlcv = await read_ohlcv_parquet(sym_key)
        if cached_ohlcv is not None and not cached_ohlcv.empty:
            raw_price = cached_ohlcv
        else:
            if not settings.backtest_allow_network_fallback:
                raise BacktestDependencyError(
                    "No cached OHLCV for backtest; run refresh-universe first "
                    "or set BACKTEST_ALLOW_NETWORK_FALLBACK=true"
                )
            raw_price = await self._market.get_daily_ohlcv(
                ticker, output_size="full", skip_cache=False
            )
        price_df = raw_price[["date", "close"]].copy()
        price_df["date"] = pd.to_datetime(price_df["date"])

        return await asyncio.to_thread(
            self._run_single_cpu,
            sym,
            model,
            price_df,
            start_date,
            end_date,
            initial_capital,
        )

    def _run_single_cpu(
        self,
        sym: str,
        model: ModelId,
        price_df: pd.DataFrame,
        start_date: date | None,
        end_date: date | None,
        initial_capital: float,
    ) -> BacktestResponse:
        """Pandas / sklearn / backtest engine — off the asyncio event loop."""
        model_cls = get_model_class(model)
        instance = model_cls()
        try:
            instance.load()
        except FileNotFoundError as e:
            raise BacktestDependencyError(str(e)) from e

        combined = self._features.build_combined(sym)
        if combined.empty:
            raise BacktestDependencyError("Combined features are empty")
        combined["date"] = pd.to_datetime(combined["date"])

        if start_date is not None:
            dt = pd.Timestamp(start_date.isoformat())
            price_df = price_df[price_df["date"] >= dt].copy()
            combined = combined[combined["date"] >= dt].copy()
        if end_date is not None:
            dt = pd.Timestamp(end_date.isoformat())
            price_df = price_df[price_df["date"] <= dt].copy()
            combined = combined[combined["date"] <= dt].copy()

        if price_df.empty or combined.empty:
            raise BacktestInputError("No data in selected date range")

        missing = [c for c in instance.feature_set if c not in combined.columns]
        if missing:
            raise BacktestDependencyError(f"Missing model feature columns: {','.join(missing[:8])}")

        x_model = combined[instance.feature_set].fillna(0.0)
        probs = instance.predict_proba(x_model)
        preds = combined[["date"]].copy()
        preds["probability"] = probs[:, 1]
        preds["signal"] = preds["probability"].map(instance.get_signal)

        engine = BacktestEngine(initial_capital=initial_capital)
        out = engine.run(price_df, preds, ticker=sym, model_id=model.value)

        curve = [
            EquityPoint(
                date=pd.Timestamp(r["date"]).date(),
                equity=float(r["equity"]),
                return_pct=float(r["return_pct"]),
                benchmark_equity=float(r["benchmark_equity"]),
            )
            for _, r in out.equity_curve.iterrows()
        ]
        return BacktestResponse(
            ticker=out.ticker,
            model=out.model_id,
            start_date=date.fromisoformat(out.start_date),
            end_date=date.fromisoformat(out.end_date),
            initial_capital=out.initial_capital,
            metrics=BacktestMetrics(
                cumulative_return=out.cumulative_return,
                annualized_return=out.annualized_return,
                sharpe_ratio=out.sharpe_ratio,
                max_drawdown=out.max_drawdown,
                win_rate=out.win_rate,
                total_trades=out.total_trades,
            ),
            equity_curve=curve,
        )

    async def compare_models(
        self,
        *,
        ticker: str,
        start_date: date | None,
        end_date: date | None,
        initial_capital: float,
    ) -> dict[str, BacktestCompareRow]:
        """
        Run backtests for all rollout models concurrently.

        Each model backtest still runs its pandas / sklearn work in a background thread
        (see run_single + _run_single_cpu), so this mostly overlaps I/O and CPU-bound work
        across the small fixed set of models (A–F).
        """

        async def _one(mid: ModelId) -> tuple[str, BacktestCompareRow]:
            try:
                res = await self.run_single(
                    ticker=ticker,
                    model=mid,
                    start_date=start_date,
                    end_date=end_date,
                    initial_capital=initial_capital,
                )
                row = BacktestCompareRow(
                    model=mid.value,
                    ok=True,
                    metrics={
                        "cumulative_return": res.metrics.cumulative_return,
                        "annualized_return": res.metrics.annualized_return,
                        "sharpe_ratio": res.metrics.sharpe_ratio,
                        "max_drawdown": res.metrics.max_drawdown,
                        "win_rate": res.metrics.win_rate,
                        "total_trades": res.metrics.total_trades,
                    },
                )
            except (BacktestDependencyError, BacktestInputError) as e:
                row = BacktestCompareRow(
                    model=mid.value,
                    ok=False,
                    error=str(e),
                )
            return mid.value, row

        pairs = await asyncio.gather(*[_one(mid) for mid in ROLLOUT_MODEL_IDS])
        return {k: v for k, v in pairs}
