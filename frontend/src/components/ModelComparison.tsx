"use client";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useModelComparison } from "@/hooks/usePrediction";
import { MODEL_LABELS_LONG, ROLLOUT_MODEL_IDS } from "@/lib/models";
import clsx from "clsx";

interface ModelComparisonProps {
  ticker: string;
}

const SIGNAL_STYLES: Record<string, string> = {
  "Strong Buy": "text-success",
  "Buy": "text-success",
  "Hold": "text-warning",
  "Sell": "text-danger",
};

export default function ModelComparison({ ticker }: ModelComparisonProps) {
  const { data, error, isLoading } = useModelComparison(ticker);

  const models = ROLLOUT_MODEL_IDS.map((id) => ({
    id,
    label: MODEL_LABELS_LONG[id] ?? id,
  }));

  if (isLoading) {
    return (
      <div
        className="relative h-36 overflow-hidden rounded-xl border border-surface-700/50 bg-surface-900/20"
        role="status"
        aria-live="polite"
      >
        <span className="sr-only">Загрузка сравнения моделей…</span>
        <div className="absolute inset-0 p-1">
          <div className="mb-3 h-3 w-56 rounded-md bg-surface-700/70 animate-pulse" />
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <div
                  className="h-3 flex-1 rounded-md bg-surface-700/50 animate-pulse"
                  style={{ animationDelay: `${i * 70}ms` }}
                />
                <div className="h-3 w-12 rounded-md bg-surface-600/40 animate-pulse" />
                <div className="h-3 w-14 rounded-md bg-surface-600/40 animate-pulse" />
                <div className="h-3 w-10 rounded-md bg-surface-600/40 animate-pulse" />
                <div className="h-3 w-10 rounded-md bg-surface-600/40 animate-pulse" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }
  if (error) {
    return <ApiErrorNotice error={error} title="Сравнение моделей недоступно" tone="warning" />;
  }

  return (
    <div className="space-y-3">
      <p className="text-xs leading-relaxed text-slate-500">
        F1 / ROC-AUC — holdout с последнего обучения на этом тикере (Postgres experiment store или
        файл <span className="font-mono text-[10px]">model_d.metrics.json</span> (и т.п.) рядом с joblib
        после <span className="font-mono text-[10px]">train_flat_demo_model.py</span>).
      </p>
      <div className="overflow-x-auto rounded-xl border border-surface-700/50">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Сравнение сигналов и метрик качества моделей по тикеру {ticker}
          </caption>
          <thead>
            <tr className="border-b border-surface-700/70 bg-surface-900/30">
              <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Модель
              </th>
              <th className="px-3 py-2.5 text-center text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Сигнал
              </th>
              <th className="px-3 py-2.5 text-center text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                P(рост)
              </th>
              <th className="px-3 py-2.5 text-center text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                F1
              </th>
              <th className="px-3 py-2.5 text-center text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                ROC-AUC
              </th>
            </tr>
          </thead>
          <tbody>
            {models.map(({ id, label }) => {
              const m = data?.comparison?.[id as keyof typeof data.comparison];
              return (
                <tr
                  key={id}
                  className="border-b border-surface-700/40 transition-colors last:border-0 hover:bg-surface-800/50"
                >
                  <td className="px-3 py-3 font-medium text-white">{label}</td>
                  <td className={clsx("px-3 py-3 text-center text-sm font-semibold", SIGNAL_STYLES[m?.signal ?? "Hold"])}>
                    {m?.signal ?? "—"}
                  </td>
                  <td className="px-3 py-3 text-center font-mono text-sm tabular-nums text-slate-300">
                    {m?.probability != null ? `${(m.probability * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-3 py-3 text-center font-mono text-sm tabular-nums text-slate-300">
                    {m?.f1?.toFixed(3) ?? "—"}
                  </td>
                  <td className="px-3 py-3 text-center font-mono text-sm tabular-nums text-slate-300">
                    {m?.roc_auc?.toFixed(3) ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
