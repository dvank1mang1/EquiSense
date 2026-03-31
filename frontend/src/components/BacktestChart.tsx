"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import {
  startBacktestJob,
  useBacktestJob,
  useBacktestPreflight,
} from "@/hooks/useBacktestJob";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface BacktestChartProps {
  ticker: string;
  model: string;
}

export default function BacktestChart({ ticker, model }: BacktestChartProps) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<unknown | null>(null);
  const { data, error } = useBacktestJob(jobId);
  const { data: preflight, error: preflightError, isLoading: isPreflightLoading } =
    useBacktestPreflight(ticker || null);

  const hasResult = data && data.status === "completed" && (data as any).result?.equity_curve?.length;

  const handleStart = async () => {
    try {
      setLastError(null);
      const resp = await startBacktestJob(ticker, { model });
      setJobId(resp.job_id);
    } catch (e) {
      setLastError(e);
    }
  };

  if (error || lastError || preflightError) {
    return (
      <ApiErrorNotice
        error={error ?? lastError ?? preflightError}
        title="Не удалось запустить или получить бэктест"
        tone="warning"
      />
    );
  }

  if (!jobId) {
    if (isPreflightLoading) {
      return <div className="h-28 animate-pulse bg-surface-700 rounded-lg" />;
    }

    const ready = preflight?.ready ?? false;
    const reason = preflight?.reason ?? "данные не готовы";
    return (
      <div className="flex flex-col items-start gap-3">
        {ready ? (
          <p className="text-slate-400 text-sm">
            Бэктест ещё не запускался для этой модели. Запустите расчёт — результат появится
            в фоне.
          </p>
        ) : (
          <div className="rounded-lg border border-amber-700/50 bg-amber-950/30 px-3 py-2 text-sm text-amber-100/90">
            <p className="font-medium text-amber-200">Данные для бэктеста не готовы</p>
            <p className="mt-1 text-slate-300">
              {reason}. Сначала запустите обновление данных (refresh-universe), затем повторите.
            </p>
            <p className="mt-2 text-xs text-slate-500">
              OHLCV cache: {preflight?.has_cached_ohlcv ? "ok" : "missing"} · combined
              features: {preflight?.has_combined_features ? "ok" : "missing"}
            </p>
          </div>
        )}
        <button
          type="button"
          onClick={handleStart}
          disabled={!ready}
          className="inline-flex items-center rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
        >
          Запустить бэктест
        </button>
      </div>
    );
  }

  if (!hasResult) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-slate-700 bg-surface-800 px-4 py-3 text-sm text-slate-300">
        <div>
          <p className="font-medium text-slate-100">Бэктест в очереди</p>
          <p className="mt-1 text-slate-400">
            Статус: {data?.status ?? "ожидание"} · job_id:{" "}
            <span className="font-mono text-xs text-slate-500">{jobId}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-xs text-slate-400">
            Рассчёт выполняется… UI не блокируется.
          </span>
        </div>
      </div>
    );
  }

  const result = (data as any).result;
  const dates = result.equity_curve.map((p: any) => p.date);
  const equity = result.equity_curve.map((p: any) => p.equity);
  const benchmark = result.equity_curve.map((p: any) => p.benchmark_equity);

  const m = result.metrics;

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
