import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useFundamentals } from "@/hooks/useStockData";
import { extractFundamentalMetrics } from "@/lib/fundamentalsDisplay";

interface FundamentalPanelProps {
  ticker: string;
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-2.5 border-b border-surface-700/60 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className="text-sm font-mono font-medium tabular-nums text-white">{value}</span>
    </div>
  );
}

function PanelSkeleton({ label }: { label: string }) {
  return (
    <div className="card" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="mb-5 space-y-2">
        <div className="h-4 w-36 rounded-md bg-surface-700/90 animate-pulse" />
        <div className="h-3 max-w-[200px] rounded-md bg-surface-700/50 animate-pulse" />
      </div>
      <div className="space-y-0">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="flex justify-between gap-4 border-b border-surface-700/40 py-2.5 last:border-0"
          >
            <div
              className="h-3 w-[45%] max-w-[100px] rounded-md bg-surface-700/70 animate-pulse"
              style={{ animationDelay: `${i * 60}ms` }}
            />
            <div
              className="h-3 w-14 rounded-md bg-surface-600/50 animate-pulse"
              style={{ animationDelay: `${i * 60 + 40}ms` }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function FundamentalPanel({ ticker }: FundamentalPanelProps) {
  const { data, error, isLoading } = useFundamentals(ticker);

  if (isLoading) {
    return <PanelSkeleton label="Загрузка фундаментальных показателей…" />;
  }
  if (error) {
    return (
      <div className="card">
        <ApiErrorNotice error={error} title="Фундаментал недоступен" />
      </div>
    );
  }

  const rawFund = data?.fundamentals;
  const f = extractFundamentalMetrics(
    rawFund && typeof rawFund === "object" && !Array.isArray(rawFund)
      ? (rawFund as Record<string, unknown>)
      : {}
  );

  return (
    <div className="card">
      <div className="mb-5">
        <h3 className="text-base font-semibold tracking-tight text-white">Фундаментал</h3>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          Ключевые мультипликаторы и доходность для контекста оценки.
        </p>
      </div>
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
