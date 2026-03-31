import useSWR from "swr";
import { api } from "@/lib/api";

/** Backtest runs pandas + optional OHLCV I/O; compare runs six models — allow > default 30s axios timeout. */
const BACKTEST_TIMEOUT_MS = 120_000;

const fetcher = (url: string) =>
  api.get(url, { timeout: BACKTEST_TIMEOUT_MS }).then((r) => r.data);

export function useBacktest(ticker: string, model: string) {
  return useSWR(ticker ? `/backtesting/${ticker}?model=${model}` : null, fetcher, {
    keepPreviousData: true,
  });
}

export function useBacktestComparison(ticker: string) {
  return useSWR(ticker ? `/backtesting/${ticker}/compare` : null, fetcher, {
    keepPreviousData: true,
  });
}
