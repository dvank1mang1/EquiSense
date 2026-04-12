import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { normalizeJsonValue } from "@/types/api";

/** Backtest runs pandas + optional OHLCV I/O; compare runs six models — allow > default 30s axios timeout. */
const BACKTEST_TIMEOUT_MS = 120_000;

const fetcher = (url: string) =>
  apiGet<any>(url, { timeout: BACKTEST_TIMEOUT_MS }, normalizeJsonValue as (data: unknown) => any);

export function useBacktest(ticker: string, model: string) {
  const qs = new URLSearchParams({ model }).toString();
  return useSWR(ticker ? `/backtesting/${ticker}?${qs}` : null, fetcher, {
    keepPreviousData: true,
  });
}

export function useBacktestComparison(ticker: string) {
  return useSWR(ticker ? `/backtesting/${ticker}/compare` : null, fetcher, {
    keepPreviousData: true,
  });
}
