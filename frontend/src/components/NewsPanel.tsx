import ApiErrorNotice from "@/components/ApiErrorNotice";
import { useNews } from "@/hooks/useStockData";
import { safeHttpUrl } from "@/lib/safeUrl";
import clsx from "clsx";

interface NewsPanelProps {
  ticker: string;
}

const SENTIMENT_BADGE: Record<string, string> = {
  positive: "border border-success/25 bg-success/15 text-success",
  negative: "border border-danger/25 bg-danger/15 text-danger",
  neutral: "border border-warning/25 bg-warning/15 text-warning",
};

function NewsPanelSkeleton() {
  return (
    <div className="card" role="status" aria-live="polite">
      <span className="sr-only">Загрузка новостей…</span>
      <div className="mb-5 space-y-2">
        <div className="h-4 w-28 rounded-md bg-surface-700/90 animate-pulse" />
        <div className="h-3 max-w-[180px] rounded-md bg-surface-700/50 animate-pulse" />
      </div>
      <div className="space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-surface-700/40 bg-surface-900/20 p-3">
            <div className="flex gap-2">
              <div className="h-3 flex-1 rounded-md bg-surface-700/70 animate-pulse" />
              <div className="h-5 w-14 shrink-0 rounded-lg bg-surface-700/50 animate-pulse" />
            </div>
            <div
              className="mt-2 h-2.5 w-2/3 rounded-md bg-surface-600/40 animate-pulse"
              style={{ animationDelay: `${i * 80}ms` }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function NewsPanel({ ticker }: NewsPanelProps) {
  const { data, error, isLoading } = useNews(ticker);

  if (isLoading) {
    return <NewsPanelSkeleton />;
  }
  if (error) {
    return (
      <div className="card">
        <ApiErrorNotice error={error} title="Новости недоступны" />
      </div>
    );
  }

  const items = Array.isArray(data?.news) ? data.news : [];

  return (
    <div className="card overflow-hidden">
      <div className="mb-4">
        <h3 className="text-base font-semibold tracking-tight text-white">Новости</h3>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          Лента с тональностью; ссылки открываются в новой вкладке.
        </p>
      </div>
      <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
        {items.length === 0 && (
          <p className="text-slate-500 text-sm" role="status">
            Новостей по этому тикеру пока нет.
          </p>
        )}
        {items.map((item: any, i: number) => {
          const href = safeHttpUrl(item.url);
          const labelBase =
            item.title && typeof item.title === "string"
              ? `${item.title}${item.source ? `, ${item.source}` : ""}`
              : "Новость";
          const inner = (
            <>
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm text-slate-300 leading-snug line-clamp-2">{item.title}</p>
                {item.sentiment && (
                  <span
                    className={clsx(
                      "inline-flex shrink-0 items-center rounded-lg px-2 py-0.5 text-xs font-medium transition-colors",
                      SENTIMENT_BADGE[item.sentiment]
                    )}
                  >
                    {item.sentiment}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {item.source} · {item.published_at}
              </p>
            </>
          );
          if (!href) {
            return (
              <div
                key={i}
                className="-mx-2 block rounded-lg border border-surface-700/40 bg-surface-900/20 p-2.5 text-slate-500"
                role="status"
              >
                {inner}
                <p className="mt-1 text-xs text-slate-600">Ссылка недоступна</p>
              </div>
            );
          }
          return (
            <a
              key={i}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="-mx-2 block rounded-lg p-2.5 transition-colors hover:border-surface-600/60 hover:bg-surface-800/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-inset border border-transparent active:bg-surface-800"
              aria-label={`${labelBase} (открывается в новой вкладке)`}
            >
              {inner}
            </a>
          );
        })}
      </div>
    </div>
  );
}
