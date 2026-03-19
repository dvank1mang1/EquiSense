"use client";
import dynamic from "next/dynamic";
import { useShapExplanation } from "@/hooks/usePrediction";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ShapChartProps {
  ticker: string;
  model: string;
}

export default function ShapChart({ ticker, model }: ShapChartProps) {
  const { data, isLoading } = useShapExplanation(ticker, model);

  if (isLoading) return <div className="h-64 animate-pulse bg-surface-700 rounded-lg" />;
  if (!data?.features?.length) return <p className="text-slate-500 text-sm">Данные недоступны — обучите модель</p>;

  const sorted = [...data.features].sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value)).slice(0, 15);
  const colors = sorted.map((f) => (f.shap_value >= 0 ? "#22c55e" : "#ef4444"));

  return (
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
        xaxis: { gridcolor: "#334155", title: "SHAP value" },
        yaxis: { automargin: true },
        margin: { t: 10, b: 40, l: 150, r: 20 },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
    />
  );
}
