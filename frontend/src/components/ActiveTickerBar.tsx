"use client";

import { X } from "lucide-react";

type ActiveTickerBarProps = {
  ticker: string;
  onClear: () => void;
};

export default function ActiveTickerBar({ ticker, onClear }: ActiveTickerBarProps) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-surface-600/70 bg-surface-850/80 px-4 py-3 shadow-sm shadow-black/20 backdrop-blur-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Активный тикер
        </span>
        <span className="font-mono text-xl font-bold tracking-tight text-white">{ticker}</span>
      </div>
      <button
        type="button"
        onClick={onClear}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-surface-600 bg-surface-800/90 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:border-surface-500 hover:bg-surface-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-850"
      >
        <X className="h-3.5 w-3.5" aria-hidden />
        Сбросить
      </button>
    </div>
  );
}
