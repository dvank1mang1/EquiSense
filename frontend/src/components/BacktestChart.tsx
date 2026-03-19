"use client";
import dynamic from "next/dynamic";
import { useBacktest } from "@/hooks/useBacktest";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface BacktestChartProps {
  ticker: string;
  model: string;
}

export default function BacktestChart({ ticker, model }: BacktestChartProps) {
  const { data, isLoading } = useBacktest(ticker, model);

  if (isLoading) return <div className="h-64 animate-pulse bg-surface-700 rounded-lg" />;
  if (!data?.equity_curve?.length) return <p className="text-slate-500 text-sm">Данные недоступны — обучите модель</p>;

  const dates = data.equity_curve.map((p: any) => p.date);
  const equity = data.equity_curve.map((p: any) => p.equity);
  const benchmark = data.equity_curve.map((p: any) => p.benchmark_equity);

  const m = data.metrics;

  return (
    <div className="space-y-4">
      {/* Metrics row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Cumulative Return", value: m?.cumulative_return != null ? `${(m.cumulative_return * 100).toFixed(1)}%` : "—" },
          { label: "Sharpe Ratio", value: m?.sharpe_ratio?.toFixed(2) ?? "—" },
          { label: "Max Drawdown", value: m?.max_drawdown != null ? `${(m.max_drawdown * 100).toFixed(1)}%` : "—" },
          { label: "Win Rate", value: m?.win_rate != null ? `${(m.win_rate * 100).toFixed(1)}%` : "—" },
        ].map((item) => (
          <div key={item.label} className="bg-surface-700 rounded-lg p-3 text-center">
            <p className="text-xs text-slate-500">{item.label}</p>
            <p className="text-xl font-bold text-white mt-1">{item.value}</p>
          </div>
        ))}
      </div>

      {/* Chart */}
      <Plot
        data={[
          { x: dates, y: equity, type: "scatter", mode: "lines", name: "Стратегия", line: { color: "#0ea5e9", width: 2 } },
          { x: dates, y: benchmark, type: "scatter", mode: "lines", name: "Buy & Hold", line: { color: "#64748b", width: 1, dash: "dash" } },
        ]}
        layout={{
          height: 300,
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { color: "#94a3b8", size: 12 },
          xaxis: { gridcolor: "#334155" },
          yaxis: { gridcolor: "#334155", tickprefix: "$" },
          margin: { t: 10, b: 40, l: 70, r: 10 },
          legend: { x: 0, y: 1, bgcolor: "transparent" },
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%" }}
      />
    </div>
  );
}
