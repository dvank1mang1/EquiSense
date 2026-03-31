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

  if (isLoading) return <div className="h-64 animate-pulse bg-surface-700 rounded-lg" />;
  if (error) {
    return <ApiErrorNotice error={error} title="SHAP недоступен" tone="warning" />;
  }
  if (!data?.features?.length) {
    return <p className="text-slate-500 text-sm">Данные недоступны — обучите модель</p>;
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
      {/* Group contributions */}
      {groups && groupTotal > 0 && (
        <div>
          <p className="text-xs text-slate-400 mb-2 uppercase tracking-wide">Вклад групп признаков</p>
          <div className="flex gap-3 flex-wrap">
            {Object.entries(groups).map(([key, val]) => {
              const pct = groupTotal > 0 ? ((val / groupTotal) * 100).toFixed(1) : "0.0";
              return (
                <div key={key} className="flex-1 min-w-[100px] bg-surface-700 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: GROUP_COLORS[key] ?? "#94a3b8" }}
                    />
                    <span className="text-xs text-slate-400">{GROUP_LABELS[key] ?? key}</span>
                  </div>
                  <p className="text-lg font-bold text-white">{pct}%</p>
                  <div className="mt-1 h-1 bg-surface-600 rounded-full overflow-hidden">
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
  );
}
