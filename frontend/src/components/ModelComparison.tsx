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
  Buy: "text-success",
  Hold: "text-warning",
  Sell: "text-danger",
};

function fmtMetric(v: unknown, digits: number, kind: "ratio" | "rate" | "plain" = "plain"): string {
  if (v === null || v === undefined) return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "—";
  if (kind === "ratio") return n.toFixed(digits);
  if (kind === "rate") return `${(n * 100).toFixed(digits)}%`;
  return n.toFixed(digits);
}

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
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Сигналы</h3>
        <div className="overflow-x-auto rounded-xl border border-surface-700/50">
          <table className="w-full text-sm">
            <caption className="sr-only">Сигналы и вероятность по моделям</caption>
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
                    <td
                      className={clsx(
                        "px-3 py-3 text-center text-sm font-semibold",
                        SIGNAL_STYLES[m?.signal ?? "Hold"]
                      )}
                    >
                      {m?.signal ?? "—"}
                    </td>
                    <td className="px-3 py-3 text-center font-mono text-sm tabular-nums text-slate-300">
                      {m?.probability != null ? `${(m.probability * 100).toFixed(1)}%` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Классификация (holdout)
        </h3>
        <div className="overflow-x-auto rounded-xl border border-surface-700/50">
          <table className="w-full min-w-[720px] text-sm">
            <caption className="sr-only">Классификационные метрики</caption>
            <thead>
              <tr className="border-b border-surface-700/70 bg-surface-900/30">
                <th className="sticky left-0 z-10 bg-surface-900/95 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  Модель
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  Acc
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  F1
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  ROC-AUC
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  PR-AUC
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  Prev+
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  PR−Prev
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  Brier
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  Prec
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  Rec
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  ECE
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
                    <td className="sticky left-0 z-10 bg-surface-900/80 px-3 py-2.5 font-medium text-white backdrop-blur-sm">
                      {label}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.accuracy, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.f1, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.roc_auc, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.pr_auc, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-400">
                      {fmtMetric(m?.test_prevalence_positive, 3, "rate")}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.pr_auc_minus_prevalence, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.brier, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.precision, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.recall, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.ece, 3)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] leading-relaxed text-slate-600">
          Prev+ — доля положительного класса на тесте. PR−Prev — средняя точность vs этот baseline
          (интерпретация PR-AUC). IC / Rank IC — серийные корреляции (по дням holdout), не
          кросс-секция; если «—», часто константные вероятности на тесте или слишком мало точек после
          dropna. L/S spread — разница средних forward return в верхнем и нижнем квантиле по score на
          holdout (для одного тикера — по времени, не по сечению).
        </p>
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Ранжирование и отбор (тест)
        </h3>
        <div className="overflow-x-auto rounded-xl border border-surface-700/50">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">Метрики ранжирования</caption>
            <thead>
              <tr className="border-b border-surface-700/70 bg-surface-900/30">
                <th className="sticky left-0 z-10 bg-surface-900/95 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  Модель
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  P@K
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  R@K
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  IC
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  Rank IC
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  IC(−s)
                </th>
                <th className="px-2 py-2.5 text-center text-[10px] font-semibold uppercase text-slate-500">
                  L/S spread
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
                    <td className="sticky left-0 z-10 bg-surface-900/80 px-3 py-2.5 font-medium text-white backdrop-blur-sm">
                      {label}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.precision_at_k, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.recall_at_k, 3)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.ic_mean, 4)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.rank_ic_mean, 4)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-400">
                      {fmtMetric(m?.ic_mean_neg_score, 4)}
                    </td>
                    <td className="px-2 py-2.5 text-center font-mono text-xs tabular-nums text-slate-300">
                      {fmtMetric(m?.long_short_spread, 4, "rate")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
