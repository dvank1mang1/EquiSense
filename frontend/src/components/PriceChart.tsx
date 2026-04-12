"use client";
import dynamic from "next/dynamic";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import { usePriceHistory } from "@/hooks/useStockData";
import { useState } from "react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const PERIODS = ["1m", "3m", "6m", "1y", "2y"];

const CHIP_BASE =
  "text-xs font-medium px-3 py-1.5 rounded-lg border transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-800 active:scale-[0.98]";
const CHIP_ON = "border-brand-500/80 bg-brand-600 text-white shadow-sm shadow-black/25";
const CHIP_OFF =
  "border-surface-600/80 bg-surface-900/30 text-slate-400 hover:border-surface-500 hover:bg-surface-800/60 hover:text-slate-200";

interface PriceChartProps {
  ticker: string;
}

export default function PriceChart({ ticker }: PriceChartProps) {
  const [period, setPeriod] = useState("1y");
  const { data, error, isLoading } = usePriceHistory(ticker, period);

  const candles = Array.isArray(data?.candles) ? data.candles : [];
  const dates = candles.map((c: { date: string }) => c.date);
  const closes = candles.map((c: { close: number }) => c.close);

  return (
    <div>
      <p className="mb-3 text-xs leading-relaxed text-slate-500">
        Цена закрытия по выбранному горизонту; ось синхронизирована с данными бэкенда.
      </p>
      <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Период графика">
        {PERIODS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPeriod(p)}
            aria-pressed={period === p}
            aria-label={`Период ${p}`}
            className={`${CHIP_BASE} ${period === p ? CHIP_ON : CHIP_OFF}`}
          >
            {p}
          </button>
        ))}
      </div>

      {error ? (
        <ApiErrorNotice error={error} title="Не удалось загрузить историю цен" />
      ) : isLoading ? (
        <div
          className="relative h-64 overflow-hidden rounded-xl border border-surface-700/50 bg-surface-900/20"
          role="status"
          aria-live="polite"
        >
          <span className="sr-only">Загрузка истории цен…</span>
          <div className="absolute inset-x-4 bottom-8 top-10 flex flex-col justify-end gap-2">
            <div className="h-px w-full bg-surface-700/40" />
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-8 w-full rounded-md bg-surface-700/50 animate-pulse"
                style={{ opacity: 1 - i * 0.12 }}
              />
            ))}
          </div>
          <div className="absolute left-4 right-4 top-6 h-3 rounded-md bg-surface-700/80 animate-pulse" />
        </div>
      ) : (
        <div aria-label={`График цены закрытия ${ticker}, период ${period}`}>
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
        </div>
      )}
    </div>
  );
}
