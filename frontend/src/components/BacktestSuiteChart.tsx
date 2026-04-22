"use client";

import { useCallback, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useBacktestPreflight } from "@/hooks/useBacktestJob";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

type SuiteStrategy = {
  group: "baseline" | "ml";
  label: string;
  ok: boolean;
  metrics?: Record<string, number> | null;
  equity_curve?: Array<{ date: string; equity: number; return_pct?: number; benchmark_equity?: number }> | null;
  error?: string | null;
};

type SuitePayload = {
  ticker: string;
  initial_capital: number;
  start_date?: string | null;
  end_date?: string | null;
  strategies: Record<string, SuiteStrategy>;
};

const TRACE_COLORS = [
  "#38bdf8",
  "#a78bfa",
  "#34d399",
  "#fbbf24",
  "#fb7185",
  "#94a3f8",
  "#2dd4bf",
  "#f472b6",
  "#c084fc",
  "#4ade80",
];

function defaultVisible(keys: string[], includeMl: string): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const k of keys) {
    out[k] = k === "buy_and_hold" || (includeMl !== "none" && k === "model_d");
  }
  return out;
}

export default function BacktestSuiteChart({ ticker }: { ticker: string }) {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [includeMl, setIncludeMl] = useState<"model_d" | "none" | "all">("model_d");
  const [suite, setSuite] = useState<SuitePayload | null>(null);
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const { data: preflight, error: pfError, isLoading: pfLoading } = useBacktestPreflight(ticker || null);

  const loadSuite = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = { include_ml: includeMl };
      if (startDate.trim()) params.start_date = startDate.trim();
      if (endDate.trim()) params.end_date = endDate.trim();
      const { data } = await api.get<SuitePayload>(`/backtesting/${ticker}/suite`, {
        params,
        timeout: 120000,
      });
      setSuite(data);
      setVisible(defaultVisible(Object.keys(data.strategies), includeMl));
    } catch (e) {
      setError(e);
      setSuite(null);
    } finally {
      setLoading(false);
    }
  }, [ticker, startDate, endDate, includeMl]);

  const baselineKeys = useMemo(
    () => (suite ? Object.keys(suite.strategies).filter((k) => suite.strategies[k].group === "baseline") : []),
    [suite]
  );
  const mlKeys = useMemo(
    () => (suite ? Object.keys(suite.strategies).filter((k) => suite.strategies[k].group === "ml") : []),
    [suite]
  );

  const plotData = useMemo(() => {
    if (!suite) return [];
    const traces: object[] = [];
    let ci = 0;
    const keys = [...baselineKeys, ...mlKeys];
    for (const id of keys) {
      if (!visible[id]) continue;
      const row = suite.strategies[id];
      if (!row.ok || !row.equity_curve?.length) continue;
      const color = TRACE_COLORS[ci % TRACE_COLORS.length];
      ci += 1;
      traces.push({
        x: row.equity_curve.map((p) => p.date),
        y: row.equity_curve.map((p) => p.equity),
        type: "scatter",
        mode: "lines",
        name: row.label,
        line: { color, width: 2 },
        hovertemplate: `${row.label}<br>%{x}<br>$%{y:,.0f}<extra></extra>`,
      });
    }
    return traces;
  }, [suite, visible, baselineKeys, mlKeys]);

  const canLoadBaselines = preflight?.ready_baseline ?? false;
  const canLoadMl = includeMl === "none" ? true : (preflight?.ready ?? false);
  const canLoad = canLoadBaselines && canLoadMl;

  if (pfLoading) {
    return (
      <div className="h-24 animate-pulse rounded-xl border border-surface-700/50 bg-surface-900/30" role="status">
        <span className="sr-only">Проверка данных…</span>
      </div>
    );
  }
  if (pfError) {
    return <ApiErrorNotice error={pfError} title="Preflight недоступен" tone="warning" />;
  }

  return (
    <div className="space-y-4">
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
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          <span className="font-medium text-slate-400">ML в ответе</span>
          <select
            value={includeMl}
            onChange={(e) => setIncludeMl(e.target.value as "model_d" | "none" | "all")}
            className="rounded-lg border border-surface-600/80 bg-surface-900/40 px-2 py-1.5 text-sm text-slate-200"
          >
            <option value="model_d">Только model_d</option>
            <option value="all">Все A–F</option>
            <option value="none">Без ML (только базлайны)</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => void loadSuite()}
          disabled={!canLoad || loading}
          className="rounded-lg border border-brand-500/40 bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-500 disabled:opacity-50"
        >
          {loading ? "Загрузка…" : "Загрузить кривые"}
        </button>
      </div>
      {!canLoad ? (
        <p className="text-sm text-amber-200/90">
          Для ML нужен ETL (technical). Для базлайнов достаточно OHLCV.{" "}
          <span className="text-slate-500">({preflight?.reason})</span>
        </p>
      ) : null}

      {error ? <ApiErrorNotice error={error} title="Не удалось загрузить suite" tone="warning" /> : null}

      {suite ? (
        <>
          <div className="grid gap-6 md:grid-cols-2">
            <fieldset className="space-y-2 rounded-xl border border-surface-700/60 bg-surface-900/20 p-4">
              <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">Базлайны</legend>
              <div className="flex flex-col gap-2">
                {baselineKeys.map((id) => {
                  const row = suite.strategies[id];
                  return (
                    <label key={id} className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                      <input
                        type="checkbox"
                        checked={!!visible[id]}
                        onChange={(e) => setVisible((v) => ({ ...v, [id]: e.target.checked }))}
                        className="rounded border-surface-600"
                      />
                      <span className={row.ok ? "" : "text-slate-500 line-through"}>{row.label}</span>
                      {!row.ok && row.error ? (
                        <span className="text-xs text-amber-400/90" title={row.error}>
                          ошибка
                        </span>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <fieldset className="space-y-2 rounded-xl border border-surface-700/60 bg-surface-900/20 p-4">
              <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">ML</legend>
              <div className="flex flex-col gap-2">
                {mlKeys.map((id) => {
                  const row = suite.strategies[id];
                  return (
                    <label key={id} className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                      <input
                        type="checkbox"
                        checked={!!visible[id]}
                        onChange={(e) => setVisible((v) => ({ ...v, [id]: e.target.checked }))}
                        className="rounded border-surface-600"
                      />
                      <span className={row.ok ? "" : "text-slate-500 line-through"}>{row.label}</span>
                      {!row.ok && row.error ? (
                        <span className="text-xs text-amber-400/90" title={row.error}>
                          ошибка
                        </span>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          </div>

          <div className="rounded-xl border border-surface-700/50 bg-surface-900/20 p-2" aria-label="Сравнение кривых капитала">
            {plotData.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-500">
                Включите хотя бы одну стратегию с успешной кривой (чекбоксы выше).
              </p>
            ) : null}
            <Plot
              data={plotData}
              layout={{
                height: 380,
                paper_bgcolor: "transparent",
                plot_bgcolor: "rgba(15,23,42,0.25)",
                font: { color: "#94a3b8", size: 12 },
                xaxis: {
                  gridcolor: "rgba(51,65,85,0.35)",
                  title: { text: "Дата" },
                  zeroline: false,
                  showline: true,
                  linecolor: "rgba(71,85,105,0.5)",
                },
                yaxis: {
                  gridcolor: "rgba(51,65,85,0.35)",
                  tickprefix: "$",
                  title: { text: "Equity" },
                  zeroline: false,
                  showline: true,
                  linecolor: "rgba(71,85,105,0.5)",
                },
                margin: { t: 24, b: 48, l: 72, r: 24 },
                legend: {
                  orientation: "h",
                  yanchor: "bottom",
                  y: 1.02,
                  xanchor: "right",
                  x: 1,
                  bgcolor: "transparent",
                  font: { size: 11 },
                },
                hovermode: "x unified",
                hoverlabel: {
                  bgcolor: "rgba(30,41,59,0.92)",
                  bordercolor: "rgba(100,116,139,0.45)",
                  font: { color: "#e2e8f0", size: 12 },
                },
              }}
              config={{ displayModeBar: true, responsive: true }}
              style={{ width: "100%" }}
            />
          </div>
        </>
      ) : (
        <p className="text-sm text-slate-500">
          Нажмите «Загрузить кривые» — один запрос к API, переключение линий без повторной загрузки.
        </p>
      )}
    </div>
  );
}
