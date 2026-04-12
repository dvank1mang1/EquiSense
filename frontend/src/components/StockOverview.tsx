import { TrendingUp, TrendingDown } from "lucide-react";
import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useStockOverview } from "@/hooks/useStockData";

interface StockOverviewProps {
  ticker: string;
}

export default function StockOverview({ ticker }: StockOverviewProps) {
  const { data, isLoading, error } = useStockOverview(ticker);

  if (isLoading) {
    return (
      <div
        className="card h-36 animate-pulse ring-1 ring-surface-700/40"
        role="status"
        aria-live="polite"
      >
        <span className="sr-only">Загрузка обзора тикера…</span>
        <div className="h-full rounded-lg bg-surface-700/80" aria-hidden />
      </div>
    );
  }
  if (error) {
    return (
      <div className="card ring-1 ring-surface-700/40">
        <h3 className="sr-only">Обзор тикера {ticker}</h3>
        <ApiErrorNotice error={error} title="Не удалось загрузить обзор тикера" />
      </div>
    );
  }

  const q = data?.quote as Record<string, unknown> | null | undefined;
  const fund = data?.fundamentals as Record<string, unknown> | null | undefined;

  const parseNumeric = (value: unknown): number | undefined => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
      const parsed = parseFloat(value.replace(/,/g, "").trim());
      if (Number.isFinite(parsed)) return parsed;
    }
    return undefined;
  };

  const price = parseNumeric(q?.price);
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
  const marketCapNum = parseNumeric(fund?.MarketCapitalization);
  const hasOverview =
    price != null ||
    changePct != null ||
    name !== "—" ||
    sector !== "—" ||
    (marketCapNum != null && !Number.isNaN(marketCapNum));

  if (!hasOverview) {
    return (
      <div className="card ring-1 ring-surface-700/40" role="status">
        <h3 className="sr-only">Обзор тикера {ticker}</h3>
        <p className="text-sm text-slate-400">Данных обзора для этого тикера пока нет.</p>
      </div>
    );
  }

  const changeLabel =
    changePct != null ? `${isPositive && changePct > 0 ? "+" : ""}${changePct.toFixed(2)}%` : "—";

  return (
    <div className="card ring-1 ring-surface-700/40 shadow-md shadow-black/10">
      <h3 className="sr-only">Обзор тикера {ticker}</h3>
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="inline-flex items-center rounded-lg border border-surface-600 bg-surface-900/50 px-2.5 py-1 font-mono text-lg font-bold tracking-tight text-white md:text-xl"
              aria-hidden
            >
              {ticker}
            </span>
            {sector !== "—" ? (
              <span className="inline-flex max-w-full items-center truncate rounded-full border border-surface-600/80 bg-surface-900/40 px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {sector}
              </span>
            ) : null}
          </div>
          <p className="text-base font-medium leading-snug text-slate-200 md:text-lg">{name}</p>
        </div>

        <div className="shrink-0 border-t border-surface-700/80 pt-4 sm:border-l sm:border-t-0 sm:pl-6 sm:pt-0 text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Цена</p>
          <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-white md:text-4xl">
            {price != null ? `$${price.toFixed(2)}` : "—"}
          </p>
          <div
            className={`mt-2 inline-flex items-center justify-end gap-1.5 rounded-full px-2.5 py-1 text-sm font-semibold tabular-nums ${
              changePct == null
                ? "bg-surface-700/50 text-slate-400"
                : isPositive
                  ? "bg-success/15 text-success"
                  : "bg-danger/15 text-danger"
            }`}
          >
            {changePct == null ? null : isPositive ? (
              <TrendingUp className="h-4 w-4 shrink-0" aria-hidden />
            ) : (
              <TrendingDown className="h-4 w-4 shrink-0" aria-hidden />
            )}
            <span>{changeLabel}</span>
          </div>
          <div className="mt-4 border-t border-surface-700/60 pt-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Рыночная капитализация</p>
            <p className="mt-1 text-sm font-medium tabular-nums text-slate-300">
              {marketCapNum != null && !Number.isNaN(marketCapNum) ? `$${(marketCapNum / 1e9).toFixed(1)}B` : "—"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
