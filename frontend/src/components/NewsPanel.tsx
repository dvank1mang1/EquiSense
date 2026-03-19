import { useNews } from "@/hooks/useStockData";
import clsx from "clsx";

interface NewsPanelProps {
  ticker: string;
}

const SENTIMENT_BADGE: Record<string, string> = {
  positive: "badge-buy",
  negative: "badge-sell",
  neutral: "badge-hold",
};

export default function NewsPanel({ ticker }: NewsPanelProps) {
  const { data, isLoading } = useNews(ticker);

  if (isLoading) return <div className="card animate-pulse h-64" />;

  return (
    <div className="card overflow-hidden">
      <h3 className="mb-4">Новости</h3>
      <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
        {(data ?? []).length === 0 && (
          <p className="text-slate-500 text-sm">Новости не найдены</p>
        )}
        {(data ?? []).map((item: any, i: number) => (
          <a
            key={i}
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block hover:bg-surface-700 rounded-lg p-2 -mx-2 transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm text-slate-300 leading-snug line-clamp-2">{item.title}</p>
              {item.sentiment && (
                <span className={clsx("text-xs shrink-0", SENTIMENT_BADGE[item.sentiment])}>
                  {item.sentiment}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">{item.source} · {item.published_at}</p>
          </a>
        ))}
      </div>
    </div>
  );
}
