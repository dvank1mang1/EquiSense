"use client";
import { useState } from "react";
import { Search } from "lucide-react";

const POPULAR_TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA", "META", "JPM"];

interface TickerSearchProps {
  onSelect: (ticker: string) => void;
}

export default function TickerSearch({ onSelect }: TickerSearchProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) {
      onSelect(input.trim().toUpperCase());
      setInput("");
    }
  };

  return (
    <div className="flex flex-col items-end gap-2">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Введите тикер..."
            className="pl-9 pr-4 py-2 bg-surface-700 border border-surface-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 text-sm w-48"
          />
        </div>
        <button type="submit" className="btn-primary text-sm">
          Анализ
        </button>
      </form>
      <div className="flex gap-1 flex-wrap justify-end">
        {POPULAR_TICKERS.map((t) => (
          <button
            key={t}
            onClick={() => onSelect(t)}
            className="text-xs px-2 py-1 rounded bg-surface-700 text-slate-400 hover:text-white hover:bg-surface-600 transition-colors font-mono"
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}
