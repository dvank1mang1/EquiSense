import { TrendingUp, TrendingDown } from "lucide-react";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useStockOverview } from "@/hooks/useStockData";

interface StockOverviewProps {
  ticker: string;
}

export default function StockOverview({ ticker }: StockOverviewProps) {
  const { data, isLoading, error } = useStockOverview(ticker);

  if (isLoading) return <div className="card animate-pulse h-32" />;
  if (error) {
    return (
      <div className="card">
        <ApiErrorNotice error={error} title="Не удалось загрузить обзор тикера" />
      </div>
    );
  }

  const q = data?.quote as Record<string, unknown> | null | undefined;
  const fund = data?.fundamentals as Record<string, unknown> | null | undefined;

  const price = typeof q?.price === "number" ? q.price : undefined;
  let changePct: number | undefined;
  if (typeof q?.change_percent === "string") {
    const p = parseFloat(String(q.change_percent).replace("%", "").trim());
    if (!Number.isNaN(p)) changePct = p;
  } else if (typeof q?.change_percent === "number") {
    changePct = q.change_percent;
  } else if (
    typeof q?.change === "number" &&
    typeof q?.previous_close === "number" &&
    q.previous_close !== 0
  ) {
    changePct = (q.change / q.previous_close) * 100;
  }

  const isPositive = (changePct ?? 0) >= 0;
  const name = typeof fund?.Name === "string" ? fund.Name : "—";
  const sector = typeof fund?.Sector === "string" ? fund.Sector : "—";
  const rawCap = fund?.MarketCapitalization;
  const marketCapNum =
    typeof rawCap === "number"
      ? rawCap
      : typeof rawCap === "string"
        ? parseFloat(rawCap)
        : undefined;

  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div>
          <span className="font-mono text-2xl font-bold text-white">{ticker}</span>
          <p className="text-slate-400 text-sm mt-1">{name}</p>
          <p className="text-xs text-slate-500 mt-1">{sector}</p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold text-white">
            {price != null ? `$${price.toFixed(2)}` : "—"}
          </p>
          <div className={`flex items-center justify-end gap-1 mt-1 ${isPositive ? "text-success" : "text-danger"}`}>
            {isPositive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            <span className="font-medium">
              {changePct != null ? `${isPositive && changePct > 0 ? "+" : ""}${changePct.toFixed(2)}%` : "—"}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Market Cap:{" "}
            {marketCapNum != null && !Number.isNaN(marketCapNum)
              ? `$${(marketCapNum / 1e9).toFixed(1)}B`
              : "—"}
          </p>
        </div>
      </div>
    </div>
  );
}
