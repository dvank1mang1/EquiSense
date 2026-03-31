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

  if (isLoading) return <div className="animate-pulse h-32 bg-surface-700 rounded-lg" />;
  if (error) {
    return <ApiErrorNotice error={error} title="Сравнение моделей недоступно" tone="warning" />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-700">
            <th className="text-left py-2 text-slate-400 font-medium">Модель</th>
            <th className="text-center py-2 text-slate-400 font-medium">Сигнал</th>
            <th className="text-center py-2 text-slate-400 font-medium">P(рост)</th>
            <th className="text-center py-2 text-slate-400 font-medium">F1</th>
            <th className="text-center py-2 text-slate-400 font-medium">ROC-AUC</th>
          </tr>
        </thead>
        <tbody>
          {models.map(({ id, label }) => {
            const m = data?.comparison?.[id as keyof typeof data.comparison];
            return (
              <tr key={id} className="border-b border-surface-700/50 hover:bg-surface-700/30">
                <td className="py-3 font-medium text-white">{label}</td>
                <td className={clsx("py-3 text-center font-semibold", SIGNAL_STYLES[m?.signal ?? "Hold"])}>
                  {m?.signal ?? "—"}
                </td>
                <td className="py-3 text-center text-slate-300 font-mono">
                  {m?.probability != null ? `${(m.probability * 100).toFixed(1)}%` : "—"}
                </td>
                <td className="py-3 text-center text-slate-300 font-mono">
                  {m?.f1?.toFixed(3) ?? "—"}
                </td>
                <td className="py-3 text-center text-slate-300 font-mono">
                  {m?.roc_auc?.toFixed(3) ?? "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
