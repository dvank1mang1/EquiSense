"use client";

import { Newspaper } from "lucide-react";
import clsx from "clsx";
import { useNews } from "@/hooks/useStockData";
import { safeHttpUrl } from "@/lib/safeUrl";

interface NewsMarqueeProps {
  /** Если null — показываем ленту по AAPL как «обзор рынка». */
  focusTicker: string | null;
}

function stripHtml(s: string) {
  return s.replace(/<[^>]*>/g, "").trim();
}

export default function NewsMarquee({ focusTicker }: NewsMarqueeProps) {
  const effective = (focusTicker || "AAPL").toUpperCase();
  const { data, error, isLoading } = useNews(effective, { limit: 14 });

  const raw = Array.isArray(data?.news) ? data.news : [];
  const serverWarning = typeof data?.warning === "string" ? data.warning : null;
  const items = raw
    .map((item: { title?: string; source?: string; url?: string }) => {
      const title = typeof item.title === "string" ? stripHtml(item.title) : "";
      if (!title) return null;
      return {
        title: title.length > 120 ? `${title.slice(0, 117)}…` : title,
        source: typeof item.source === "string" ? item.source : "—",
        href: safeHttpUrl(item.url),
      };
    })
    .filter(Boolean) as { title: string; source: string; href: string | null }[];

  const fallback = [
    {
      title: "Лента подтягивается из API: задайте ключи новостей и выполните refresh по тикеру.",
      source: "EquiSense",
      href: null as string | null,
    },
  ];

  const row = items.length > 0 ? items : fallback;
  const doubled = [...row, ...row];

  return (
    <div
      className="relative overflow-hidden border-y border-white/[0.06] bg-gradient-to-r from-surface-900/90 via-surface-900/70 to-surface-900/90"
      role="region"
      aria-label="Лента заголовков новостей"
    >
      <div
        className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-surface-950 to-transparent"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-surface-950 to-transparent"
        aria-hidden
      />

      <div className="mx-auto flex max-w-7xl items-stretch gap-0 px-0 sm:px-2">
        <div
          className="flex shrink-0 items-center gap-2 border-r border-white/[0.06] bg-surface-950/40 px-3 py-2.5 sm:px-4"
          title={
            [focusTicker ? `Новости: ${effective}` : `Обзор: ${effective} (выберите тикер — лента переключится)`, serverWarning]
              .filter(Boolean)
              .join(" — ") || undefined
          }
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-brand-500/25 bg-brand-500/10 text-brand-400">
            <Newspaper className="h-4 w-4" strokeWidth={2} aria-hidden />
          </span>
          <div className="hidden min-w-0 sm:block">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-brand-400/90">Новости</p>
            <p className="truncate font-mono text-[11px] text-slate-500">{effective}</p>
          </div>
        </div>

        <div className="relative min-h-[44px] min-w-0 flex-1 overflow-hidden py-2 pr-2">
          {isLoading && (
            <div className="flex h-full items-center px-4">
              <div className="h-2.5 w-full max-w-md rounded-full bg-surface-700/50 animate-pulse" />
            </div>
          )}
          {error && !isLoading && (
            <p className="flex h-full items-center px-4 text-xs text-amber-200/80">
              Лента недоступна (проверьте API и ключи новостей).
            </p>
          )}
          {!isLoading && !error && (
            <div className="news-marquee-hover group flex h-full items-center">
              <div className="news-marquee-track flex w-max items-center gap-10 pr-8">
                {doubled.map((item, i) => (
                  <span key={i} className="flex shrink-0 items-center gap-2 text-sm text-slate-300">
                    <span className="h-1 w-1 shrink-0 rounded-full bg-brand-400/80" aria-hidden />
                    {item.href ? (
                      <a
                        href={item.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="max-w-[min(72vw,28rem)] truncate text-slate-200 transition-colors hover:text-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 rounded-sm"
                      >
                        {item.title}
                      </a>
                    ) : (
                      <span className="max-w-[min(72vw,28rem)] truncate text-slate-400">{item.title}</span>
                    )}
                    <span className={clsx("shrink-0 font-mono text-[10px] uppercase tracking-wide", item.href ? "text-slate-500" : "text-slate-600")}>
                      {item.source}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
