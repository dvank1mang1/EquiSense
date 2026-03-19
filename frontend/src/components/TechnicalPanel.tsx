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
    <div className="flex justify-between items-center py-2 border-b border-surface-700 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className={`text-sm font-mono font-medium ${colorMap[highlight ?? "neutral"]}`}>{value}</span>
    </div>
  );
}

export default function TechnicalPanel({ ticker }: TechnicalPanelProps) {
  const { data, isLoading } = useTechnicalIndicators(ticker);

  if (isLoading) return <div className="card animate-pulse h-64" />;

  return (
    <div className="card">
      <h3 className="mb-4">Технические индикаторы</h3>
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
