import useSWR from "swr";
import { api } from "@/lib/api";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export function useBacktest(ticker: string, model: string) {
  return useSWR(
    ticker ? `/backtesting/${ticker}?model=${model}` : null,
    fetcher
  );
}

export function useBacktestComparison(ticker: string) {
  return useSWR(ticker ? `/backtesting/${ticker}/compare` : null, fetcher);
}
