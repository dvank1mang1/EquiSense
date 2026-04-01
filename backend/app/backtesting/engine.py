from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    ticker: str
    model_id: str
    start_date: str
    end_date: str
    initial_capital: float
    cumulative_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    equity_curve: pd.DataFrame
    turnover: float = 0.0


class BacktestEngine:
    """
    Симулирует торговую стратегию на основе предсказаний ML-модели.

    Satisfies :class:`app.contracts.backtesting.BacktestRunner` when ``run`` is implemented.

    Стратегия:
        - Long позиция при сигнале Buy / Strong Buy
        - Выход при сигнале Sell или Hold (в зависимости от настроек)
        - No short selling (для упрощения)

    Метрики:
        - Cumulative Return
        - Annualized Return
        - Sharpe Ratio (risk-free rate = 0)
        - Max Drawdown
        - Win Rate
    """

    def __init__(self, initial_capital: float = 10000.0, risk_free_rate: float = 0.0):
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate

    def run(
        self,
        price_df: pd.DataFrame,
        predictions_df: pd.DataFrame,
        ticker: str,
        model_id: str,
    ) -> BacktestResult:
        """
        Запустить backtesting.

        Args:
            price_df: DataFrame с колонками date, close
            predictions_df: DataFrame с колонками date, probability, signal
            ticker: тикер акции
            model_id: идентификатор модели

        Returns:
            BacktestResult с метриками и equity curve
        """
        if price_df.empty or predictions_df.empty:
            raise ValueError("price_df and predictions_df must be non-empty")
        required_price = {"date", "close"}
        required_pred = {"date", "signal"}
        if not required_price.issubset(price_df.columns):
            raise ValueError(f"price_df must contain {sorted(required_price)}")
        if not required_pred.issubset(predictions_df.columns):
            raise ValueError(f"predictions_df must contain {sorted(required_pred)}")

        p = price_df.copy()
        p["date"] = pd.to_datetime(p["date"])
        p = p.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        s = predictions_df.copy()
        s["date"] = pd.to_datetime(s["date"])
        s = s.sort_values("date").drop_duplicates(subset=["date"], keep="last")

        merged = p[["date", "close"]].merge(s[["date", "signal"]], on="date", how="inner")
        if merged.empty:
            raise ValueError("No overlapping dates between price and predictions")

        # Long-only regime: enter on Buy/Strong Buy, flat on Hold/Sell.
        merged["position"] = (
            merged["signal"].map({"Strong Buy": 1, "Buy": 1, "Hold": 0, "Sell": 0}).fillna(0)
        )
        merged["asset_ret"] = merged["close"].pct_change().fillna(0.0)
        merged["strategy_ret"] = merged["position"].shift(1).fillna(0.0) * merged["asset_ret"]
        merged["equity"] = self.initial_capital * (1.0 + merged["strategy_ret"]).cumprod()
        merged["benchmark_equity"] = self.initial_capital * (1.0 + merged["asset_ret"]).cumprod()
        merged["return_pct"] = (merged["equity"] / self.initial_capital) - 1.0

        # Derive trades from position transitions (0->1 enter, 1->0 exit).
        trades: list[dict[str, float]] = []
        in_pos = False
        entry_equity = 0.0
        for _, row in merged.iterrows():
            pos = int(row["position"])
            eq = float(row["equity"])
            if not in_pos and pos == 1:
                in_pos = True
                entry_equity = eq
            elif in_pos and pos == 0:
                in_pos = False
                trades.append({"pnl_pct": (eq / entry_equity) - 1.0})
        if in_pos:
            last_eq = float(merged["equity"].iloc[-1])
            trades.append({"pnl_pct": (last_eq / entry_equity) - 1.0})

        cumulative_return = float((merged["equity"].iloc[-1] / self.initial_capital) - 1.0)
        n_days = max(1, len(merged))
        annualized_return = float((1.0 + cumulative_return) ** (252.0 / n_days) - 1.0)
        sharpe_ratio = self._compute_sharpe(merged["strategy_ret"])
        max_drawdown = self._compute_max_drawdown(merged["equity"])
        win_rate = self._compute_win_rate(trades)
        turnover = float(merged["position"].diff().abs().fillna(merged["position"].iloc[0]).mean())

        return BacktestResult(
            ticker=ticker.upper(),
            model_id=model_id,
            start_date=merged["date"].iloc[0].strftime("%Y-%m-%d"),
            end_date=merged["date"].iloc[-1].strftime("%Y-%m-%d"),
            initial_capital=float(self.initial_capital),
            cumulative_return=cumulative_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            total_trades=len(trades),
            turnover=turnover,
            equity_curve=merged[["date", "equity", "return_pct", "benchmark_equity"]].copy(),
        )

    def _compute_sharpe(self, returns: pd.Series) -> float:
        """Рассчитать Sharpe Ratio (дневные доходности, annualized)."""
        if returns.empty:
            return 0.0
        excess = returns - (self.risk_free_rate / 252.0)
        std = float(excess.std(ddof=0))
        if std <= 1e-12:
            return 0.0
        return float((excess.mean() / std) * np.sqrt(252.0))

    def _compute_max_drawdown(self, equity: pd.Series) -> float:
        """Рассчитать максимальную просадку."""
        if equity.empty:
            return 0.0
        peak = equity.cummax()
        dd = (equity / peak) - 1.0
        return float(dd.min())

    def _compute_win_rate(self, trades: list[dict]) -> float:
        """Рассчитать долю прибыльных сделок."""
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if float(t.get("pnl_pct", 0.0)) > 0.0)
        return float(wins / len(trades))

    def run_cross_sectional_top_k(
        self,
        panel_df: pd.DataFrame,
        *,
        score_col: str = "score",
        return_col: str = "forward_return",
        top_k: int = 10,
    ) -> dict[str, float]:
        """
        Ranking backtest: each date buy top-K by model score, equal-weight.
        """
        req = {"date", "ticker", score_col, return_col}
        if not req.issubset(panel_df.columns):
            raise ValueError(f"panel_df must contain {sorted(req)}")
        d = panel_df[list(req)].dropna().copy()
        d["date"] = pd.to_datetime(d["date"])
        if d.empty:
            raise ValueError("panel_df has no valid rows")
        rows: list[dict[str, float | pd.Timestamp]] = []
        for dt, g in d.groupby("date"):
            gs = g.sort_values(score_col, ascending=False)
            k = max(1, min(int(top_k), len(gs)))
            top = gs.iloc[:k]
            bottom = gs.iloc[-k:]
            rows.append(
                {
                    "date": dt,
                    "top_ret": float(top[return_col].mean()),
                    "bottom_ret": float(bottom[return_col].mean()),
                }
            )
        daily = pd.DataFrame(rows).sort_values("date")
        daily["long_short_ret"] = daily["top_ret"] - daily["bottom_ret"]
        daily["curve_long_short"] = (1.0 + daily["long_short_ret"]).cumprod()
        daily["curve_long_only"] = (1.0 + daily["top_ret"]).cumprod()
        turnover = (
            d.sort_values(["date", score_col], ascending=[True, False])
            .groupby("date")
            .head(max(1, top_k))[["date", "ticker"]]
        )
        turns = []
        prev: set[str] = set()
        for _, g in turnover.groupby("date"):
            curr = set(g["ticker"].astype(str))
            if not prev:
                turns.append(1.0)
            else:
                turns.append(1.0 - (len(prev & curr) / max(1, len(curr))))
            prev = curr
        return {
            "topk_mean_return": float(daily["top_ret"].mean()),
            "bottomk_mean_return": float(daily["bottom_ret"].mean()),
            "long_short_mean_return": float(daily["long_short_ret"].mean()),
            "long_short_sharpe": self._compute_sharpe(daily["long_short_ret"]),
            "long_only_sharpe": self._compute_sharpe(daily["top_ret"]),
            "turnover": float(np.mean(turns)) if turns else 0.0,
        }
