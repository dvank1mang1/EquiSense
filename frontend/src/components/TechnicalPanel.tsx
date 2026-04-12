import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useTechnicalIndicators } from "@/hooks/useStockData";

interface TechnicalPanelProps {
  ticker: string;
}

function MetricRow({ label, value, highlight }: { label: string; value: string; highlight?: "positive" | "negative" | "neutral" }) {
  const colorMap = {
    positive: "text-success",
    negative: "text-danger",
    neutral: "text-white",
  };
  return (
    <div className="flex justify-between items-center py-2.5 border-b border-surface-700/60 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className={`text-sm font-mono font-medium tabular-nums ${colorMap[highlight ?? "neutral"]}`}>{value}</span>
    </div>
  );
}

function PanelSkeleton({ label }: { label: string }) {
  return (
    <div className="card" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="mb-5 space-y-2">
        <div className="h-4 w-44 rounded-md bg-surface-700/90 animate-pulse" />
        <div className="h-3 max-w-[220px] rounded-md bg-surface-700/50 animate-pulse" />
      </div>
      <div className="space-y-0">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex justify-between gap-4 border-b border-surface-700/40 py-2.5 last:border-0"
          >
            <div
              className="h-3 w-[40%] max-w-[120px] rounded-md bg-surface-700/70 animate-pulse"
              style={{ animationDelay: `${i * 60}ms` }}
            />
            <div
              className="h-3 w-16 rounded-md bg-surface-600/50 animate-pulse"
              style={{ animationDelay: `${i * 60 + 40}ms` }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TechnicalPanel({ ticker }: TechnicalPanelProps) {
  const { data, error, isLoading } = useTechnicalIndicators(ticker);

  if (isLoading) {
    return <PanelSkeleton label="Загрузка технических индикаторов…" />;
  }
  if (error) {
    return (
      <div className="card">
        <ApiErrorNotice error={error} title="Индикаторы недоступны" />
      </div>
    );
  }

  return (
    <div className="card">
      <div className="mb-5">
        <h3 className="text-base font-semibold tracking-tight text-white">Технические индикаторы</h3>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          Краткий снимок импульса и тренда по последним расчётам.
        </p>
      </div>
      <MetricRow label="RSI (14)" value={data?.rsi?.toFixed(1) ?? "—"} highlight={data?.rsi > 70 ? "negative" : data?.rsi < 30 ? "positive" : "neutral"} />
      <MetricRow label="MACD" value={data?.macd?.toFixed(3) ?? "—"} highlight={data?.macd > 0 ? "positive" : "negative"} />
      <MetricRow label="SMA 20" value={data?.sma_20?.toFixed(2) ?? "—"} />
      <MetricRow label="SMA 50" value={data?.sma_50?.toFixed(2) ?? "—"} />
      <MetricRow label="SMA 200" value={data?.sma_200?.toFixed(2) ?? "—"} />
      <MetricRow label="BB Upper" value={data?.bb_upper?.toFixed(2) ?? "—"} />
      <MetricRow label="BB Lower" value={data?.bb_lower?.toFixed(2) ?? "—"} />
      <MetricRow label="Volatility" value={data?.volatility?.toFixed(3) ?? "—"} />
    </div>
  );
}
