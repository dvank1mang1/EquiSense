from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.backtesting.baseline_signals import (
    CANONICAL_RULE_STRATEGY_IDS,
    is_rule_backtest_strategy,
    rule_strategy_predictions,
    suite_strategy_label,
)
from app.backtesting.engine import BacktestEngine
from app.contracts.data_providers import MarketDataProvider
from app.contracts.features import FeatureStorePort
from app.core.config import settings
from app.data.persistence import read_ohlcv_parquet
from app.data.utils import normalize_ticker
from app.domain.exceptions import BacktestDependencyError, BacktestInputError
from app.domain.identifiers import ROLLOUT_MODEL_IDS, FeatureSlice, ModelId
from app.models import get_model_class
from app.schemas.backtest import BacktestMetrics, BacktestResponse, EquityPoint


def _ml_suite_label(model_id: str) -> str:
    m = model_id.strip().lower()
    names = {
        "model_a": "ML A (technical)",
        "model_b": "ML B (tech + fund)",
        "model_c": "ML C (tech + news)",
        "model_d": "ML D (all features)",
        "model_e": "ML E (HGBM all)",
        "model_f": "ML F (voting)",
    }
    return names.get(m, f"ML {m}")


def _backtest_remote_ohlcv_allowed() -> bool:
    """Network OHLCV for backtests when explicitly allowed or Alpha Vantage is configured."""
    if settings.backtest_allow_network_fallback:
        return True
    return bool((settings.alpha_vantage_api_key or "").strip())


def _resolve_feature_set(instance: object) -> list[str]:
    expected = getattr(instance, "expected_feature_set", None)
    if callable(expected):
        out = expected()
        if isinstance(out, list):
            return [str(v) for v in out]
    raw = getattr(instance, "feature_set", [])
    if isinstance(raw, list):
        return [str(v) for v in raw]
    return []


def _validate_feature_columns(instance: object, frame: pd.DataFrame) -> list[str]:
    checker = getattr(instance, "ensure_feature_columns", None)
    if callable(checker):
        checker(frame)
        return _resolve_feature_set(instance)
    required = _resolve_feature_set(instance)
    available = [c for c in required if c in frame.columns]
    if available:
        return available
    if required:
        preview = ",".join(required[:8])
        raise ValueError(f"Missing model feature columns: {preview}")
    raise ValueError("Model has empty feature_set")


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
        # ETL writes technical/fundamental/sentiment Parquet; combined is built in memory via
        # build_combined() (there is usually no combined.parquet on disk).
        has_technical = self._features.exists(sym, FeatureSlice.TECHNICAL.value)
        remote_ok = _backtest_remote_ohlcv_allowed()

        price_ready = has_cached_ohlcv or remote_ok
        ready_ml = has_technical and price_ready
        ready_baseline = price_ready
        reason = ""
        if not has_cached_ohlcv and not has_technical:
            reason = "нет кэшированного OHLCV и обработанных технических фич"
        elif not has_cached_ohlcv:
            reason = (
                "OHLCV подтянется из Alpha Vantage при запуске бэктеста (локального кэша нет)"
                if remote_ok
                else "нет кэшированного OHLCV в data/raw/ohlcv — задайте ALPHA_VANTAGE_API_KEY, "
                "BACKTEST_ALLOW_NETWORK_FALLBACK=true или выполните refresh-universe"
            )
        elif not has_technical:
            reason = "нет processed/technical (запустите ETL: refresh-universe с run_etl или download_ohlcv_dataset … --run-etl)"

        return {
            "ticker": sym,
            "ready": ready_ml,
            "ready_baseline": ready_baseline,
            "has_cached_ohlcv": has_cached_ohlcv,
            # Имя поля историческое: True, если можно собрать combined (есть technical.parquet).
            "has_combined_features": has_technical,
            "has_processed_technical": has_technical,
            "reason": reason,
        }

    async def run_single(
        self,
        *,
        ticker: str,
        model: str | ModelId,
        start_date: date | None,
        end_date: date | None,
        initial_capital: float,
    ) -> BacktestResponse:
        sym = ticker.strip().upper()
        sym_key = normalize_ticker(ticker)
        model_key = model.value if isinstance(model, ModelId) else str(model).strip()
        # Local OHLCV first (see GET /stocks/{ticker}/history) — avoids Alpha Vantage per model on /compare.
        cached_ohlcv = await read_ohlcv_parquet(sym_key)
        if cached_ohlcv is not None and not cached_ohlcv.empty:
            raw_price = cached_ohlcv
        else:
            if not _backtest_remote_ohlcv_allowed():
                raise BacktestDependencyError(
                    "No cached OHLCV for backtest; run refresh-universe first or set "
                    "ALPHA_VANTAGE_API_KEY (or BACKTEST_ALLOW_NETWORK_FALLBACK=true)"
                )
            raw_price = await self._market.get_daily_ohlcv(
                ticker, output_size="full", skip_cache=False
            )
        ohlcv = raw_price.copy()
        ohlcv["date"] = pd.to_datetime(ohlcv["date"])
        if "volume" not in ohlcv.columns:
            ohlcv["volume"] = 0.0
        else:
            ohlcv["volume"] = pd.to_numeric(ohlcv["volume"], errors="coerce").fillna(0.0)
        price_df = ohlcv[["date", "close"]].copy()

        if is_rule_backtest_strategy(model_key):
            return await asyncio.to_thread(
                self._run_rule_strategy_cpu,
                sym,
                model_key,
                ohlcv,
                start_date,
                end_date,
                initial_capital,
            )

        mid = ModelId(model_key)
        return await asyncio.to_thread(
            self._run_single_cpu,
            sym,
            mid,
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

        try:
            features = _validate_feature_columns(instance, combined)
        except ValueError as e:
            raise BacktestDependencyError(str(e)) from e
        x_model = combined[features].fillna(0.0)
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
                turnover=out.turnover,
            ),
            equity_curve=curve,
        )

    def _run_rule_strategy_cpu(
        self,
        sym: str,
        strategy_id: str,
        ohlcv: pd.DataFrame,
        start_date: date | None,
        end_date: date | None,
        initial_capital: float,
    ) -> BacktestResponse:
        p = ohlcv.copy()
        p["date"] = pd.to_datetime(p["date"])
        if start_date is not None:
            dt = pd.Timestamp(start_date.isoformat())
            p = p[p["date"] >= dt].copy()
        if end_date is not None:
            dt = pd.Timestamp(end_date.isoformat())
            p = p[p["date"] <= dt].copy()
        if p.empty:
            raise BacktestInputError("No data in selected date range")
        price_for_engine = p[["date", "close"]].copy()
        preds = rule_strategy_predictions(strategy_id, p)
        engine = BacktestEngine(initial_capital=initial_capital)
        out = engine.run(price_for_engine, preds, ticker=sym, model_id=strategy_id)
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
                turnover=out.turnover,
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
                    model=mid.value,
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
                        "turnover": float(res.metrics.turnover or 0.0),
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
        out: dict[str, BacktestCompareRow] = {k: v for k, v in pairs}

        async def _baseline_row(bid: str) -> tuple[str, BacktestCompareRow]:
            try:
                res = await self.run_single(
                    ticker=ticker,
                    model=bid,
                    start_date=start_date,
                    end_date=end_date,
                    initial_capital=initial_capital,
                )
                row = BacktestCompareRow(
                    model=bid,
                    ok=True,
                    metrics={
                        "cumulative_return": res.metrics.cumulative_return,
                        "annualized_return": res.metrics.annualized_return,
                        "sharpe_ratio": res.metrics.sharpe_ratio,
                        "max_drawdown": res.metrics.max_drawdown,
                        "win_rate": res.metrics.win_rate,
                        "total_trades": res.metrics.total_trades,
                        "turnover": float(res.metrics.turnover or 0.0),
                    },
                )
            except (BacktestDependencyError, BacktestInputError) as e:
                row = BacktestCompareRow(model=bid, ok=False, error=str(e))
            return bid, row

        rule_ids = list(CANONICAL_RULE_STRATEGY_IDS)
        base_pairs = await asyncio.gather(*[_baseline_row(rid) for rid in rule_ids])
        out.update(dict(base_pairs))
        return out

    async def compare_strategy_suite(
        self,
        *,
        ticker: str,
        start_date: date | None,
        end_date: date | None,
        initial_capital: float,
        include_ml: str = "model_d",
    ) -> dict[str, dict]:
        """
        One-shot metrics + equity curves for rule strategies and selected ML models.

        ``include_ml``: ``model_d`` | ``none`` | ``all`` | comma-separated model ids.
        """

        async def _rule_row(sid: str) -> tuple[str, dict]:
            try:
                res = await self.run_single(
                    ticker=ticker,
                    model=sid,
                    start_date=start_date,
                    end_date=end_date,
                    initial_capital=initial_capital,
                )
                return sid, {
                    "group": "baseline",
                    "label": suite_strategy_label(sid),
                    "ok": True,
                    "metrics": res.metrics.model_dump(),
                    "equity_curve": [pt.model_dump() for pt in res.equity_curve],
                    "error": None,
                }
            except (BacktestDependencyError, BacktestInputError) as e:
                return sid, {
                    "group": "baseline",
                    "label": suite_strategy_label(sid),
                    "ok": False,
                    "metrics": None,
                    "equity_curve": None,
                    "error": str(e),
                }

        rule_keys = list(CANONICAL_RULE_STRATEGY_IDS)
        rule_part = await asyncio.gather(*[_rule_row(sid) for sid in rule_keys])
        out: dict[str, dict] = {k: v for k, v in rule_part}

        raw_ml = (include_ml or "model_d").strip().lower()
        ml_ids: list[str] = []
        if raw_ml == "none":
            pass
        elif raw_ml == "all":
            ml_ids = [m.value for m in ROLLOUT_MODEL_IDS]
        elif "," in raw_ml:
            ml_ids = [x.strip() for x in raw_ml.split(",") if x.strip()]
        else:
            ml_ids = [raw_ml]

        async def _ml_row(mid: str) -> tuple[str, dict]:
            try:
                _ = ModelId(mid)
            except ValueError:
                return mid, {
                    "group": "ml",
                    "label": _ml_suite_label(mid),
                    "ok": False,
                    "metrics": None,
                    "equity_curve": None,
                    "error": f"unknown model id: {mid!r}",
                }
            try:
                res = await self.run_single(
                    ticker=ticker,
                    model=mid,
                    start_date=start_date,
                    end_date=end_date,
                    initial_capital=initial_capital,
                )
                return mid, {
                    "group": "ml",
                    "label": _ml_suite_label(mid),
                    "ok": True,
                    "metrics": res.metrics.model_dump(),
                    "equity_curve": [pt.model_dump() for pt in res.equity_curve],
                    "error": None,
                }
            except (BacktestDependencyError, BacktestInputError) as e:
                return mid, {
                    "group": "ml",
                    "label": _ml_suite_label(mid),
                    "ok": False,
                    "metrics": None,
                    "equity_curve": None,
                    "error": str(e),
                }

        if ml_ids:
            ml_part = await asyncio.gather(*[_ml_row(m) for m in ml_ids])
            out.update(dict(ml_part))
        return out
