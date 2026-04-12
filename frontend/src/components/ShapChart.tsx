"use client";
import dynamic from "next/dynamic";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useShapExplanation } from "@/hooks/usePrediction";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ShapChartProps {
  ticker: string;
  model: string;
}

const GROUP_LABELS: Record<string, string> = {
  technical: "Технические",
  fundamental: "Фундаментальные",
  news: "Новости",
};

const GROUP_COLORS: Record<string, string> = {
  technical: "#6366f1",
  fundamental: "#f59e0b",
  news: "#22c55e",
};

export default function ShapChart({ ticker, model }: ShapChartProps) {
  const { data, error, isLoading } = useShapExplanation(ticker, model);

  if (isLoading) {
    return (
      <div
        className="relative h-64 overflow-hidden rounded-xl border border-surface-700/50 bg-surface-900/20"
        role="status"
        aria-live="polite"
      >
        <span className="sr-only">Загрузка SHAP…</span>
        <div className="absolute inset-4 flex flex-col gap-3">
          <div className="flex gap-2">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-16 flex-1 rounded-xl border border-surface-700/40 bg-surface-800/40 animate-pulse"
                style={{ animationDelay: `${i * 100}ms` }}
              />
            ))}
          </div>
          <div className="flex flex-1 flex-col justify-center gap-2 pl-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <div
                  className="h-2 flex-1 rounded-md bg-surface-700/60 animate-pulse"
                  style={{ animationDelay: `${i * 80}ms` }}
                />
                <div className="h-2 w-8 rounded-md bg-surface-600/40 animate-pulse" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }
  if (error) {
    return <ApiErrorNotice error={error} title="SHAP недоступен" tone="warning" />;
  }
  if (!data?.features?.length) {
    return (
      <p className="rounded-xl border border-surface-700/50 bg-surface-900/20 px-4 py-3 text-sm leading-relaxed text-slate-500" role="status">
        Данных SHAP пока нет — проверьте обучение модели.
      </p>
    );
  }

  const sorted = [...data.features]
    .sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value))
    .slice(0, 15);
  const colors = sorted.map((f) => (f.shap_value >= 0 ? "#22c55e" : "#ef4444"));

  const groups = data.group_contributions as Record<string, number> | undefined;
  const groupTotal = groups
    ? Object.values(groups).reduce((s, v) => s + v, 0)
    : 0;

  return (
    <div className="space-y-6">
      <p className="text-xs leading-relaxed text-slate-500">
        Вклад признаков и групп в итоговый прогноз; горизонтальный график — топ-15 по |SHAP|.
      </p>
      {/* Group contributions */}
      {groups && groupTotal > 0 && (
        <div>
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Вклад групп признаков</p>
          <div className="flex flex-wrap gap-3">
            {Object.entries(groups).map(([key, val]) => {
              const pct = groupTotal > 0 ? ((val / groupTotal) * 100).toFixed(1) : "0.0";
              return (
                <div
                  key={key}
                  className="min-w-[108px] flex-1 rounded-xl border border-surface-700/60 bg-surface-900/25 p-3 shadow-sm shadow-black/5"
                >
                  <div className="mb-1.5 flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-white/10"
                      style={{ backgroundColor: GROUP_COLORS[key] ?? "#94a3b8" }}
                    />
                    <span className="text-xs font-medium text-slate-400">{GROUP_LABELS[key] ?? key}</span>
                  </div>
                  <p className="text-lg font-bold tabular-nums tracking-tight text-white">{pct}%</p>
                  <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-700/80">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: GROUP_COLORS[key] ?? "#94a3b8",
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Waterfall bar chart */}
      <div aria-label={`Важность признаков SHAP для ${ticker}, модель ${model}`}>
        <Plot
          data={[
            {
              type: "bar",
              orientation: "h",
              x: sorted.map((f) => f.shap_value),
              y: sorted.map((f) => f.name),
              marker: { color: colors },
            },
          ]}
          layout={{
            height: 400,
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#94a3b8", size: 11 },
            xaxis: {
              gridcolor: "#334155",
              title: { text: "SHAP value" },
              zerolinecolor: "#475569",
            },
            yaxis: { automargin: true },
            margin: { t: 10, b: 40, l: 150, r: 20 },
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: "100%" }}
        />
      </div>
    </div>
  );
}
