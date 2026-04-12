"use client";
import { useState } from "react";
import { Search } from "lucide-react";
import { normalizeTicker } from "@/lib/ticker";

const POPULAR_TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA", "META", "JPM"];

interface TickerSearchProps {
  onSelect: (ticker: string) => void;
}

export default function TickerSearch({ onSelect }: TickerSearchProps) {
  const [input, setInput] = useState("");
  const [hint, setHint] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const normalized = normalizeTicker(input);
    if (!normalized) {
      setHint("Введите корректный тикер: буквы, цифры, точка или дефис, до 15 символов.");
      return;
    }
    setHint(null);
    onSelect(normalized);
    setInput("");
  };

  return (
    <div className="flex w-full flex-col gap-3 sm:items-end">
      <form
        onSubmit={handleSubmit}
        className="flex w-full flex-col gap-2 sm:flex-row sm:items-stretch sm:justify-end"
        role="search"
        aria-label="Поиск тикера"
      >
        <div
          className="group relative flex min-w-0 flex-1 rounded-xl border border-surface-600/90 bg-surface-900/40 shadow-sm transition-all duration-200 focus-within:border-brand-500/60 focus-within:ring-2 focus-within:ring-brand-500/30 focus-within:shadow-md focus-within:shadow-brand-500/5 sm:max-w-xs sm:flex-none md:max-w-[14rem] lg:max-w-xs"
        >
          <Search
            className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 transition-colors duration-200 group-focus-within:text-brand-400"
            aria-hidden
          />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Тикер (например AAPL)"
            aria-label="Тикер для анализа"
            aria-invalid={hint ? true : undefined}
            aria-describedby={hint ? "ticker-search-hint" : undefined}
            autoComplete="off"
            className="w-full rounded-xl border-0 bg-transparent py-2.5 pl-10 pr-4 text-sm font-medium text-white placeholder:text-slate-500 transition-colors duration-200 focus-visible:outline-none"
          />
        </div>
        <button
          type="submit"
          className="btn-primary text-sm shrink-0 transition-all duration-200 active:scale-[0.98] sm:px-5"
        >
          Анализ
        </button>
      </form>
      {hint ? (
        <p id="ticker-search-hint" className="text-xs text-danger max-w-md text-left sm:text-right" role="alert">
          {hint}
        </p>
      ) : null}
      <div
        className="flex flex-wrap gap-1.5 sm:justify-end"
        role="group"
        aria-label="Популярные тикеры"
      >
        {POPULAR_TICKERS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => onSelect(t)}
            aria-label={`Выбрать тикер ${t}`}
            className="rounded-full border border-surface-600/80 bg-surface-800/80 px-2.5 py-1 text-xs font-mono font-medium text-slate-400 shadow-sm transition-all duration-200 hover:border-surface-500 hover:bg-surface-700 hover:text-white active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-900"
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}
