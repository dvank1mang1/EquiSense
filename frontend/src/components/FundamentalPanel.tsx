import ApiErrorNotice from "@/components/ApiErrorNotice";
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

type FundSnapshot = {
  pe_ratio?: number;
  eps?: number;
  revenue_growth?: number;
  roe?: number;
  debt_to_equity?: number;
  dividend_yield?: number;
};

export default function FundamentalPanel({ ticker }: FundamentalPanelProps) {
  const { data, error, isLoading } = useFundamentals(ticker);

  if (isLoading) return <div className="card animate-pulse h-64" />;
  if (error) {
    return (
      <div className="card">
        <ApiErrorNotice error={error} title="Фундаментал недоступен" />
      </div>
    );
  }

  const f = (data?.fundamentals ?? {}) as FundSnapshot;

  return (
    <div className="card">
      <h3 className="mb-4">Фундаментал</h3>
      <MetricRow label="P/E Ratio" value={f.pe_ratio != null ? f.pe_ratio.toFixed(1) : "—"} />
      <MetricRow label="EPS" value={f.eps != null ? `$${f.eps.toFixed(2)}` : "—"} />
      <MetricRow
        label="Revenue Growth"
        value={f.revenue_growth != null ? `${(f.revenue_growth * 100).toFixed(1)}%` : "—"}
      />
      <MetricRow label="ROE" value={f.roe != null ? `${(f.roe * 100).toFixed(1)}%` : "—"} />
      <MetricRow label="Debt/Equity" value={f.debt_to_equity != null ? f.debt_to_equity.toFixed(2) : "—"} />
      <MetricRow
        label="Dividend Yield"
        value={f.dividend_yield != null ? `${(f.dividend_yield * 100).toFixed(2)}%` : "—"}
      />
    </div>
  );
}
