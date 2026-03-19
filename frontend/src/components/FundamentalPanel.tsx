import { useFundamentals } from "@/hooks/useStockData";

interface FundamentalPanelProps {
  ticker: string;
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-surface-700 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className="text-sm font-mono font-medium text-white">{value}</span>
    </div>
  );
}

export default function FundamentalPanel({ ticker }: FundamentalPanelProps) {
  const { data, isLoading } = useFundamentals(ticker);

  if (isLoading) return <div className="card animate-pulse h-64" />;

  return (
    <div className="card">
      <h3 className="mb-4">Фундаментал</h3>
      <MetricRow label="P/E Ratio" value={data?.pe_ratio?.toFixed(1) ?? "—"} />
      <MetricRow label="EPS" value={data?.eps != null ? `$${data.eps.toFixed(2)}` : "—"} />
      <MetricRow label="Revenue Growth" value={data?.revenue_growth != null ? `${(data.revenue_growth * 100).toFixed(1)}%` : "—"} />
      <MetricRow label="ROE" value={data?.roe != null ? `${(data.roe * 100).toFixed(1)}%` : "—"} />
      <MetricRow label="Debt/Equity" value={data?.debt_to_equity?.toFixed(2) ?? "—"} />
      <MetricRow label="Dividend Yield" value={data?.dividend_yield != null ? `${(data.dividend_yield * 100).toFixed(2)}%` : "—"} />
    </div>
  );
}
