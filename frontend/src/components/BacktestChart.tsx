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
  /** Пустая строка = весь доступный диапазон (как на бэкенде). */
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const { data, error } = useBacktestJob(jobId);
  const { data: preflight, error: preflightError, isLoading: isPreflightLoading } =
    useBacktestPreflight(ticker || null);

  const hasResult = data && data.status === "completed" && (data as any).result?.equity_curve?.length;
  const isFailed = data?.status === "failed";
  const isTerminalIncomplete =
    data?.status === "completed" && !(data as { result?: { equity_curve?: unknown[] } }).result?.equity_curve?.length;

  const handleStart = async () => {
    try {
      setLastError(null);
      if (startDate && endDate && startDate > endDate) {
        setLastError(new Error("Дата «с» не может быть позже даты «по»."));
        return;
      }
      const body: Parameters<typeof startBacktestJob>[1] = { model };
      if (startDate.trim()) body.start_date = startDate.trim();
      if (endDate.trim()) body.end_date = endDate.trim();
      const resp = await startBacktestJob(ticker, body);
      setJobId(resp.job_id);
    } catch (e) {
      setLastError(e);
    }
  };

  const handleResetJob = () => {
    setJobId(null);
    setLastError(null);
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
      return (
        <div
          className="relative h-28 overflow-hidden rounded-xl border border-surface-700/50 bg-surface-900/20"
          role="status"
          aria-live="polite"
        >
          <span className="sr-only">Проверка готовности данных для бэктеста…</span>
          <div className="flex h-full flex-col justify-center gap-2 px-4 py-3">
            <div className="h-3 w-48 rounded-md bg-surface-700/80 animate-pulse" />
            <div className="h-3 w-full max-w-md rounded-md bg-surface-700/50 animate-pulse" />
            <div className="h-8 w-36 rounded-lg bg-surface-700/40 animate-pulse [animation-delay:120ms]" />
          </div>
        </div>
      );
    }

    const ready = preflight?.ready ?? false;
    const reason = preflight?.reason ?? "данные не готовы";
    return (
      <div className="flex flex-col items-start gap-4">
        {ready ? (
          <div className="flex w-full max-w-lg flex-col gap-3">
            <p className="text-sm leading-relaxed text-slate-400">
              Бэктест ещё не запускался для этой модели. По умолчанию — весь доступный диапазон
              цен; можно сузить период.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-slate-500">
                <span className="font-medium text-slate-400">С даты</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="rounded-lg border border-surface-600/80 bg-surface-900/40 px-2 py-1.5 text-sm text-slate-200"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slate-500">
                <span className="font-medium text-slate-400">По дату</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="rounded-lg border border-surface-600/80 bg-surface-900/40 px-2 py-1.5 text-sm text-slate-200"
                />
              </label>
            </div>
          </div>
        ) : (
          <div
            className="w-full max-w-xl rounded-xl border border-amber-500/20 border-l-4 border-l-amber-400/30 bg-amber-950/20 p-4 text-sm text-slate-200 shadow-sm shadow-black/10"
            role="status"
          >
            <p className="text-sm font-medium tracking-tight text-amber-100/95">Данные для бэктеста не готовы</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              {reason}. Сначала запустите обновление данных (refresh-universe), затем повторите.
            </p>
            <p className="mt-3 rounded-md bg-black/20 px-2 py-1.5 font-mono text-[11px] text-slate-500">
              OHLCV (raw): {preflight?.has_cached_ohlcv ? "ok" : "missing"} · technical ETL:{" "}
              {preflight?.has_processed_technical ? "ok" : "missing"}
            </p>
          </div>
        )}
        <button
          type="button"
          onClick={handleStart}
          disabled={!ready}
          aria-disabled={!ready}
          className="inline-flex items-center rounded-lg border border-brand-500/30 bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm shadow-black/20 transition-all duration-150 hover:bg-brand-500 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-800 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50"
        >
          Запустить бэктест
        </button>
      </div>
    );
  }

  if (isFailed) {
    const msg = (data as { error?: string }).error ?? "Бэктест завершился с ошибкой.";
    return (
      <div
        className="flex flex-col gap-3 rounded-xl border border-red-500/25 border-l-4 border-l-red-400/40 bg-red-950/20 px-4 py-3 text-sm text-slate-200 shadow-sm shadow-black/10"
        role="alert"
      >
        <div>
          <p className="text-sm font-medium tracking-tight text-red-100/95">Бэктест не выполнен</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">
            Статус: failed · job_id:{" "}
            <span className="font-mono text-[11px] text-slate-500">{jobId}</span>
          </p>
          <p className="mt-2 rounded-md bg-black/25 px-2 py-1.5 text-xs leading-relaxed text-slate-300">{msg}</p>
        </div>
        <button
          type="button"
          onClick={handleResetJob}
          className="self-start rounded-lg border border-surface-600/60 bg-surface-800/80 px-3 py-2 text-xs font-medium text-slate-200 transition-colors hover:bg-surface-700/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          Сбросить и запустить снова
        </button>
      </div>
    );
  }

  if (isTerminalIncomplete) {
    return (
      <div className="flex flex-col gap-3 rounded-xl border border-amber-500/20 bg-amber-950/15 px-4 py-3 text-sm text-slate-200">
        <p className="text-sm font-medium text-amber-100/90">Результат бэктеста без кривой капитала</p>
        <p className="text-xs text-slate-400">
          job_id: <span className="font-mono text-[11px]">{jobId}</span> — проверьте логи воркера или повторите запуск.
        </p>
        <button
          type="button"
          onClick={handleResetJob}
          className="self-start rounded-lg border border-surface-600/60 bg-surface-800/80 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-surface-700/80"
        >
          Сбросить
        </button>
      </div>
    );
  }

  if (!hasResult) {
    const waiting = data?.status === "queued" || data?.status === "running";
    return (
      <div
        className="flex flex-col gap-3 rounded-xl border border-surface-700/70 bg-surface-800/80 px-4 py-3 text-sm text-slate-300 shadow-sm shadow-black/10 sm:flex-row sm:items-center sm:justify-between"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <div>
          <p className="text-sm font-medium tracking-tight text-white">
            {waiting ? "Бэктест в очереди или выполняется" : "Ожидание статуса бэктеста"}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">
            Статус: {data?.status ?? "ожидание"} · job_id:{" "}
            <span className="font-mono text-[11px] text-slate-500">{jobId}</span>
          </p>
        </div>
        {waiting ? (
          <div className="flex items-center gap-2 rounded-lg border border-surface-700/50 bg-surface-900/30 px-2.5 py-1.5">
            <span className="h-2 w-2 shrink-0 rounded-full bg-amber-400/90 animate-pulse" aria-hidden />
            <span className="text-xs text-slate-400">Рассчёт выполняется… UI не блокируется.</span>
          </div>
        ) : null}
      </div>
    );
  }

  const result = (data as any).result;
  const dates = result.equity_curve.map((p: any) => p.date);
  const equity = result.equity_curve.map((p: any) => p.equity);
  const benchmark = result.equity_curve.map((p: any) => p.benchmark_equity);

  const m = result.metrics;

  return (
    <div className="space-y-5">
      <p className="text-xs leading-relaxed text-slate-500">
        Итоговые метрики и кривая капитала относительно buy &amp; hold по выбранной модели.
        {result?.start_date && result?.end_date ? (
          <span className="mt-1 block text-slate-400">
            Период симуляции: {String(result.start_date)} — {String(result.end_date)}
          </span>
        ) : null}
      </p>
      {/* Metrics row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
        {[
          { label: "Cumulative Return", value: m?.cumulative_return != null ? `${(m.cumulative_return * 100).toFixed(1)}%` : "—" },
          { label: "Sharpe Ratio", value: m?.sharpe_ratio?.toFixed(2) ?? "—" },
          { label: "Max Drawdown", value: m?.max_drawdown != null ? `${(m.max_drawdown * 100).toFixed(1)}%` : "—" },
          { label: "Win Rate", value: m?.win_rate != null ? `${(m.win_rate * 100).toFixed(1)}%` : "—" },
        ].map((item) => (
          <div
            key={item.label}
            className="rounded-xl border border-surface-700/60 bg-surface-900/25 p-3 text-center shadow-sm shadow-black/5"
          >
            <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{item.label}</p>
            <p className="mt-1.5 text-xl font-bold tabular-nums tracking-tight text-white">{item.value}</p>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div aria-label={`Кривая капитала бэктеста ${ticker}, модель ${model}`}>
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
    </div>
  );
}
