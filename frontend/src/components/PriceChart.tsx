"use client";
import dynamic from "next/dynamic";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import { usePriceHistory } from "@/hooks/useStockData";
import { lineSeriesWithGapBreaks } from "@/lib/chartGapBreaks";
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
  const meta = data?.meta as { rows?: number; warnings?: string[] } | undefined;
  const { x: plotDates, y: plotCloses } = lineSeriesWithGapBreaks(dates, closes, 10);

  const qualityNotes = (meta?.warnings ?? []).map((w) => {
    switch (w) {
      case "long_calendar_gaps":
        return "Большие календарные разрывы между барами — в кэше OHLCV дырка по датам. Перезагрузите ряд (скрипт download_ohlcv_dataset или refresh в UI).";
      case "sparse_daily_bars":
        return "Очень мало дневных точек на длинном интервале — график может выглядеть как прямая. Обновите OHLCV (refresh-universe).";
      case "constant_close":
        return "Close не меняется по выборке — проверьте кэш OHLCV.";
      default:
        return w;
    }
  });

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
          {qualityNotes.length > 0 ? (
            <div
              className="mb-3 rounded-lg border border-amber-500/25 bg-amber-950/20 px-3 py-2 text-xs leading-relaxed text-amber-100/90"
              role="status"
            >
              <p className="font-medium text-amber-100/95">Качество ряда цен</p>
              <ul className="mt-1 list-inside list-disc text-slate-300">
                {qualityNotes.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
              {typeof meta?.rows === "number" ? (
                <p className="mt-1.5 font-mono text-[10px] text-slate-500">rows={meta.rows}</p>
              ) : null}
            </div>
          ) : null}
          <Plot
            data={[
              {
                x: plotDates,
                y: plotCloses,
                type: "scatter",
                mode: "lines",
                connectgaps: false,
                line: { color: "#0ea5e9", width: 2 },
                name: ticker,
              },
            ]}
            layout={{
              height: 300,
              paper_bgcolor: "transparent",
              plot_bgcolor: "rgba(15,23,42,0.25)",
              font: { color: "#94a3b8", size: 12 },
              xaxis: {
                gridcolor: "rgba(51,65,85,0.35)",
                showgrid: true,
                zeroline: false,
                showline: true,
                linecolor: "rgba(71,85,105,0.5)",
              },
              yaxis: {
                gridcolor: "rgba(51,65,85,0.35)",
                showgrid: true,
                zeroline: false,
                showline: true,
                linecolor: "rgba(71,85,105,0.5)",
              },
              margin: { t: 10, b: 40, l: 60, r: 10 },
              showlegend: false,
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
      )}
    </div>
  );
}
