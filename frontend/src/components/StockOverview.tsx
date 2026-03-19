import { TrendingUp, TrendingDown } from "lucide-react";
import { useStockOverview } from "@/hooks/useStockData";

interface StockOverviewProps {
  ticker: string;
}

export default function StockOverview({ ticker }: StockOverviewProps) {
  const { data, isLoading, error } = useStockOverview(ticker);

  if (isLoading) return <div className="card animate-pulse h-32" />;
  if (error) return <div className="card text-danger">Ошибка загрузки данных</div>;

  const isPositive = (data?.change_pct ?? 0) >= 0;

  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div>
          <span className="font-mono text-2xl font-bold text-white">{ticker}</span>
          <p className="text-slate-400 text-sm mt-1">{data?.name ?? "—"}</p>
          <p className="text-xs text-slate-500 mt-1">{data?.sector ?? "—"}</p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold text-white">
            ${data?.price?.toFixed(2) ?? "—"}
          </p>
          <div className={`flex items-center justify-end gap-1 mt-1 ${isPositive ? "text-success" : "text-danger"}`}>
            {isPositive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            <span className="font-medium">
              {isPositive ? "+" : ""}{data?.change_pct?.toFixed(2) ?? "—"}%
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Market Cap: {data?.market_cap ? `$${(data.market_cap / 1e9).toFixed(1)}B` : "—"}
          </p>
        </div>
      </div>
    </div>
  );
}
