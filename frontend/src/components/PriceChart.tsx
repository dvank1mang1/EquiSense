"use client";
import dynamic from "next/dynamic";
import { usePriceHistory } from "@/hooks/useStockData";
import { useState } from "react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const PERIODS = ["1m", "3m", "6m", "1y", "2y"];

interface PriceChartProps {
  ticker: string;
}

export default function PriceChart({ ticker }: PriceChartProps) {
  const [period, setPeriod] = useState("1y");
  const { data, isLoading } = usePriceHistory(ticker, period);

  const dates = data?.map((c: any) => c.date) ?? [];
  const closes = data?.map((c: any) => c.close) ?? [];

  return (
    <div>
      <div className="flex gap-2 mb-4">
        {PERIODS.map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`text-xs px-3 py-1 rounded ${period === p ? "bg-brand-600 text-white" : "text-slate-400 hover:text-white"}`}
          >
            {p}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="h-64 animate-pulse bg-surface-700 rounded-lg" />
      ) : (
        <Plot
          data={[
            {
              x: dates,
              y: closes,
              type: "scatter",
              mode: "lines",
              line: { color: "#0ea5e9", width: 2 },
              name: ticker,
            },
          ]}
          layout={{
            height: 300,
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#94a3b8", size: 12 },
            xaxis: { gridcolor: "#334155", showgrid: true },
            yaxis: { gridcolor: "#334155", showgrid: true },
            margin: { t: 10, b: 40, l: 60, r: 10 },
            showlegend: false,
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: "100%" }}
        />
      )}
    </div>
  );
}
