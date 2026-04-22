"use client";

import { useCallback, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import clsx from "clsx";
import useSWR from "swr";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useBacktestPreflight } from "@/hooks/useBacktestJob";
import { MODEL_LABELS_LONG, ROLLOUT_MODEL_IDS, type RolloutModelId } from "@/lib/models";
import { apiGet, apiPost, getClientError } from "@/lib/api";
import { normalizeJsonValue, type JsonValue } from "@/types/api";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const BACKTEST_TIMEOUT_MS = 120_000;

const JOB_URL = (jobId: string) => `/backtesting/jobs/${jobId}`;
const RUN_URL = (ticker: string) => `/backtesting/${ticker}/run`;

/** Okabe–Ito (colorblind-friendly), максимально различимы на тёмном фоне */
const EQUITY_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9"];

function equityDateLabel(v: unknown): string {
  if (typeof v === "string") return v.length >= 10 ? v.slice(0, 10) : v;
  if (v instanceof Date && !Number.isNaN(v.getTime())) return v.toISOString().slice(0, 10);
  const s = String(v ?? "");
  return s.length >= 10 ? s.slice(0, 10) : s;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseJobStatus(data: unknown): {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  result?: JsonValue;
  error?: string;
} {
  if (!isRecord(data) || typeof data.job_id !== "string" || typeof data.status !== "string") {
    throw new Error("Invalid backtest job status payload.");
  }
  const status = data.status;
  if (status === "queued" || status === "running") {
    return { job_id: data.job_id, status };
  }
  if (status === "completed") {
    return {
      job_id: data.job_id,
      status: "completed",
      result: normalizeJsonValue(data.result),
    };
  }
  if (status === "failed") {
    return {
      job_id: data.job_id,
      status: "failed",
      error: typeof data.error === "string" ? data.error : undefined,
    };
  }
  throw new Error(`Unknown backtest job status: ${status}`);
}

function parseStartResponse(data: unknown): { job_id: string; status: string } {
  if (!isRecord(data) || typeof data.job_id !== "string" || typeof data.status !== "string") {
    throw new Error("Invalid backtest job creation response.");
  }
  return { job_id: data.job_id, status: data.status };
}

type JobMap = Partial<Record<RolloutModelId, string>>;

function stableJobKey(ticker: string, jobs: JobMap): string | null {
  const entries = (Object.entries(jobs) as [string, string][]).filter(([, id]) => Boolean(id));
  if (!ticker || entries.length === 0) return null;
  entries.sort((a, b) => a[0].localeCompare(b[0]));
  return `bt-multi:${ticker}:${entries.map(([m, id]) => `${m}=${id}`).join("|")}`;
}

export default function CompareMlBacktestPanel({ ticker }: { ticker: string }) {
  const { data: preflight, error: preflightError, isLoading: pfLoading } = useBacktestPreflight(ticker || null);
  const [selected, setSelected] = useState<Record<RolloutModelId, boolean>>(() =>
    Object.fromEntries(ROLLOUT_MODEL_IDS.map((id) => [id, true])) as Record<RolloutModelId, boolean>
  );
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [jobIds, setJobIds] = useState<JobMap>({});
  const [startError, setStartError] = useState<unknown>(null);
  const [starting, setStarting] = useState(false);

  const selectedIds = useMemo(
    () => ROLLOUT_MODEL_IDS.filter((id) => selected[id]),
    [selected]
  );
  const selectedCount = selectedIds.length;

  const swrKey = stableJobKey(ticker, jobIds);

  const { data: jobStates, error: pollError } = useSWR(
    swrKey,
    async () => {
      const entries = Object.entries(jobIds) as [RolloutModelId, string][];
      const out: Partial<
        Record<
          RolloutModelId,
          { job_id: string; status: "queued" | "running" | "completed" | "failed"; result?: JsonValue; error?: string }
        >
      > = {};
      await Promise.all(
        entries.map(async ([model, jobId]) => {
          if (!jobId) return;
          const raw = await apiGet<unknown>(JOB_URL(jobId), { timeout: BACKTEST_TIMEOUT_MS });
          out[model] = parseJobStatus(raw);
        })
      );
      return out;
    },
    {
      refreshInterval: (latest) => {
        if (!latest) return 2000;
        const vals = Object.values(latest);
        if (vals.some((v) => v.status === "queued" || v.status === "running")) return 2000;
        return 0;
      },
      dedupingInterval: 800,
      revalidateOnFocus: true,
      shouldRetryOnError: (err) => getClientError(err).retryable,
    }
  );

  const toggle = useCallback((id: RolloutModelId) => {
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const selectAll = useCallback(() => {
    setSelected(Object.fromEntries(ROLLOUT_MODEL_IDS.map((id) => [id, true])) as Record<RolloutModelId, boolean>);
  }, []);

  const selectNone = useCallback(() => {
    setSelected(Object.fromEntries(ROLLOUT_MODEL_IDS.map((id) => [id, false])) as Record<RolloutModelId, boolean>);
  }, []);

  const handleReset = useCallback(() => {
    setJobIds({});
    setStartError(null);
    setStarting(false);
  }, []);

  const handleRun = useCallback(async () => {
    setStartError(null);
    if (startDate && endDate && startDate > endDate) {
      setStartError(new Error("Дата «с» не может быть позже даты «по»."));
      return;
    }
    if (selectedIds.length === 0) {
      setStartError(new Error("Выберите хотя бы одну модель."));
      return;
    }
    setStarting(true);
    setJobIds({});
    try {
      const next: JobMap = {};
      await Promise.all(
        selectedIds.map(async (model) => {
          const body: { model: string; start_date?: string; end_date?: string } = { model };
          if (startDate.trim()) body.start_date = startDate.trim();
          if (endDate.trim()) body.end_date = endDate.trim();
          const resp = await apiPost<{ job_id: string; status: string }>(
            RUN_URL(ticker),
            body,
            { timeout: BACKTEST_TIMEOUT_MS },
            parseStartResponse
          );
          next[model] = resp.job_id;
        })
      );
      setJobIds(next);
    } catch (e) {
      setStartError(e);
    } finally {
      setStarting(false);
    }
  }, [ticker, selectedIds, startDate, endDate]);

  const ready = preflight?.ready ?? false;
  const reason = preflight?.reason ?? "данные не готовы";

  const plotPayload = useMemo(() => {
    if (!jobStates) return null;
    type TraceSpec = {
      x: (string | null)[];
      y: (number | null)[];
      name: string;
      line: { color: string; width: number; dash?: string };
      kind: "model" | "benchmark";
    };
    const modelTraces: TraceSpec[] = [];
    let bestBench: { x: (string | null)[]; y: (number | null)[]; n: number } | null = null;
    let colorIdx = 0;

    for (const model of ROLLOUT_MODEL_IDS) {
      const st = jobStates[model];
      if (!st || st.status !== "completed" || !st.result || typeof st.result !== "object") continue;
      const r = st.result as Record<string, unknown>;
      const curve = r.equity_curve;
      if (!Array.isArray(curve) || curve.length === 0) continue;
      const dates = curve.map((p: unknown) => {
        if (!isRecord(p)) return "";
        return equityDateLabel(p.date);
      });
      const equity = curve.map((p: unknown) => {
        if (!isRecord(p)) return null;
        const e = p.equity;
        return typeof e === "number" && Number.isFinite(e) ? e : null;
      });
      const benchmark = curve.map((p: unknown) => {
        if (!isRecord(p)) return null;
        const e = p.benchmark_equity;
        return typeof e === "number" && Number.isFinite(e) ? e : null;
      });
      const color = EQUITY_COLORS[colorIdx % EQUITY_COLORS.length];
      colorIdx += 1;
      modelTraces.push({
        x: dates,
        y: equity,
        name: MODEL_LABELS_LONG[model] ?? model,
        line: { color, width: 2.4 },
        kind: "model",
      });
      if (benchmark.some((v) => v != null)) {
        const n = curve.length;
        if (!bestBench || n > bestBench.n) {
          bestBench = { x: dates, y: benchmark, n };
        }
      }
    }

    const traces: TraceSpec[] = [];
    if (bestBench) {
      traces.push({
        x: bestBench.x,
        y: bestBench.y,
        name: "Buy & hold (бенчмарк)",
        line: { color: "rgba(148,163,184,0.55)", width: 2, dash: "dash" },
        kind: "benchmark",
      });
    }
    traces.push(...modelTraces);

    return traces.length ? traces : null;
  }, [jobStates]);

  if (preflightError) {
    return <ApiErrorNotice error={preflightError} title="Preflight бэктеста" tone="warning" />;
  }

  if (pfLoading) {
    return (
      <div
        className="relative h-28 overflow-hidden rounded-xl border border-surface-700/50 bg-surface-900/20"
        role="status"
      >
        <span className="sr-only">Проверка данных…</span>
        <div className="flex h-full flex-col justify-center gap-2 px-4 py-3">
          <div className="h-3 w-48 rounded-md bg-surface-700/80 animate-pulse" />
          <div className="h-3 w-full max-w-md rounded-md bg-surface-700/50 animate-pulse" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <p className="text-sm leading-relaxed text-slate-400">
        Выберите rollout-модели и запустите один общий прогон: для каждой модели создаётся job{" "}
        <span className="font-mono text-[11px]">POST /backtesting/…/run</span>, кривые капитала на одном графике.
        Стратегия та же, что на дашборде: long при Buy / Strong Buy, вне рынка иначе; серая пунктирная линия — buy
        &amp; hold (по самому длинному ряду среди завершённых job). Если несколько моделей почти не торговали,
        кривые могут совпадать у стартового капитала — тогда визуально сольётся одна линия, пока сигналы не разойдутся.
      </p>

      {!ready ? (
        <div
          className="w-full max-w-xl rounded-xl border border-amber-500/20 border-l-4 border-l-amber-400/30 bg-amber-950/20 p-4 text-sm text-slate-200"
          role="status"
        >
          <p className="font-medium text-amber-100/95">Данные для бэктеста не готовы</p>
          <p className="mt-2 text-sm text-slate-400">{reason}</p>
          <p className="mt-3 rounded-md bg-black/20 px-2 py-1.5 font-mono text-[11px] text-slate-500">
            OHLCV: {preflight?.has_cached_ohlcv ? "ok" : "missing"} · technical ETL:{" "}
            {preflight?.has_processed_technical ? "ok" : "missing"}
          </p>
        </div>
      ) : null}

      <fieldset
        disabled={!ready}
        className={clsx("space-y-3 rounded-xl border border-surface-700/60 bg-surface-900/20 p-4", !ready && "opacity-60")}
      >
        <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Модели в бэктесте</legend>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={selectAll}
            className="rounded-md border border-surface-600/80 bg-surface-800/60 px-2.5 py-1 text-xs text-slate-300 hover:bg-surface-700/60"
          >
            Все
          </button>
          <button
            type="button"
            onClick={selectNone}
            className="rounded-md border border-surface-600/80 bg-surface-800/60 px-2.5 py-1 text-xs text-slate-300 hover:bg-surface-700/60"
          >
            Снять все
          </button>
          <span className="self-center text-xs text-slate-500">выбрано: {selectedCount}</span>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Модели">
          {ROLLOUT_MODEL_IDS.map((id) => (
            <label
              key={id}
              className={clsx(
                "flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
                selected[id]
                  ? "border-brand-500/50 bg-brand-600/15 text-white"
                  : "border-surface-600/70 bg-surface-900/40 text-slate-400 hover:border-surface-500"
              )}
            >
              <input
                type="checkbox"
                className="h-3.5 w-3.5 rounded border-surface-500 text-brand-600 focus:ring-brand-500"
                checked={selected[id]}
                onChange={() => toggle(id)}
              />
              <span>{MODEL_LABELS_LONG[id] ?? id}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          <span className="font-medium text-slate-400">С даты</span>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            disabled={!ready}
            className="rounded-lg border border-surface-600/80 bg-surface-900/40 px-2 py-1.5 text-sm text-slate-200 disabled:opacity-50"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-500">
          <span className="font-medium text-slate-400">По дату</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            disabled={!ready}
            className="rounded-lg border border-surface-600/80 bg-surface-900/40 px-2 py-1.5 text-sm text-slate-200 disabled:opacity-50"
          />
        </label>
      </div>

      {startError ? <ApiErrorNotice error={startError} title="Не удалось запустить бэктесты" tone="warning" /> : null}
      {pollError ? <ApiErrorNotice error={pollError} title="Ошибка опроса job" tone="warning" /> : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleRun}
          disabled={!ready || starting || selectedCount === 0}
          className="inline-flex items-center rounded-lg border border-brand-500/30 bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-500 disabled:pointer-events-none disabled:opacity-50"
        >
          {starting ? "Запуск…" : "Запустить бэктест выбранных"}
        </button>
        {Object.keys(jobIds).length > 0 ? (
          <button
            type="button"
            onClick={handleReset}
            className="rounded-lg border border-surface-600/80 bg-surface-800/80 px-3 py-2 text-sm text-slate-200 hover:bg-surface-700/80"
          >
            Сбросить
          </button>
        ) : null}
      </div>

      {jobStates && selectedIds.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-surface-700/50">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">Статус бэктестов по моделям</caption>
            <thead>
              <tr className="border-b border-surface-700/70 bg-surface-900/40 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-3 py-2">Модель</th>
                <th className="px-3 py-2">Статус</th>
                <th className="px-3 py-2">Cum. return</th>
                <th className="px-3 py-2">Sharpe</th>
                <th className="px-3 py-2">Max DD</th>
              </tr>
            </thead>
            <tbody>
              {selectedIds.map((model) => {
                const st = jobStates[model];
                const label = MODEL_LABELS_LONG[model] ?? model;
                if (!st) {
                  return (
                    <tr key={model} className="border-b border-surface-800/80">
                      <td className="px-3 py-2 font-medium text-white">{label}</td>
                      <td className="px-3 py-2 text-slate-500" colSpan={4}>
                        —
                      </td>
                    </tr>
                  );
                }
                if (st.status === "failed") {
                  return (
                    <tr key={model} className="border-b border-surface-800/80">
                      <td className="px-3 py-2 font-medium text-white">{label}</td>
                      <td className="px-3 py-2 text-red-300" colSpan={4}>
                        failed{st.error ? `: ${st.error}` : ""}
                      </td>
                    </tr>
                  );
                }
                if (st.status === "queued" || st.status === "running") {
                  return (
                    <tr key={model} className="border-b border-surface-800/80">
                      <td className="px-3 py-2 font-medium text-white">{label}</td>
                      <td className="px-3 py-2 text-amber-200/90" colSpan={4}>
                        {st.status}…
                      </td>
                    </tr>
                  );
                }
                const r = st.result;
                const m =
                  r && typeof r === "object" && "metrics" in r && isRecord((r as { metrics: unknown }).metrics)
                    ? ((r as { metrics: Record<string, unknown> }).metrics as Record<string, unknown>)
                    : null;
                const cr = m?.cumulative_return;
                const sh = m?.sharpe_ratio;
                const dd = m?.max_drawdown;
                return (
                  <tr key={model} className="border-b border-surface-800/80 last:border-0">
                    <td className="px-3 py-2 font-medium text-white">{label}</td>
                    <td className="px-3 py-2 text-emerald-300/90">completed</td>
                    <td className="px-3 py-2 font-mono tabular-nums text-slate-300">
                      {typeof cr === "number" && Number.isFinite(cr) ? `${(cr * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums text-slate-300">
                      {typeof sh === "number" && Number.isFinite(sh) ? sh.toFixed(2) : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums text-slate-300">
                      {typeof dd === "number" && Number.isFinite(dd) ? `${(dd * 100).toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {plotPayload && plotPayload.length > 0 ? (
        <div aria-label="Совмещённые кривые капитала ML-моделей">
          <Plot
            data={plotPayload.map((t) => {
              const line =
                t.line.dash === "dash"
                  ? { color: t.line.color, width: t.line.width, dash: "dash" as const }
                  : { color: t.line.color, width: t.line.width };
              return {
                x: t.x,
                y: t.y,
                type: "scatter" as const,
                mode: "lines" as const,
                connectgaps: false,
                name: t.name,
                line,
                hovertemplate:
                  t.kind === "benchmark"
                    ? "%{fullData.name}<br>%{x|%Y-%m-%d}<br>$%{y:,.0f}<extra></extra>"
                    : "%{fullData.name}<br>%{x|%Y-%m-%d}<br>$%{y:,.0f}<extra></extra>",
              };
            })}
            layout={{
              height: 340,
              paper_bgcolor: "transparent",
              plot_bgcolor: "rgba(15,23,42,0.25)",
              font: { color: "#94a3b8", size: 12 },
              xaxis: {
                gridcolor: "rgba(51,65,85,0.35)",
                zeroline: false,
                showline: true,
                linecolor: "rgba(71,85,105,0.5)",
              },
              yaxis: {
                gridcolor: "rgba(51,65,85,0.35)",
                zeroline: false,
                tickprefix: "$",
                showline: true,
                linecolor: "rgba(71,85,105,0.5)",
              },
              margin: { t: 10, b: 44, l: 70, r: 10 },
              legend: { orientation: "h", y: -0.22, bgcolor: "transparent", font: { size: 11 } },
              hoverlabel: {
                bgcolor: "rgba(30,41,59,0.92)",
                bordercolor: "rgba(100,116,139,0.45)",
                font: { color: "#e2e8f0", size: 12 },
              },
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%" }}
          />
        </div>
      ) : null}
    </div>
  );
}
