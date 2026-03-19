import useSWR from "swr";
import { api } from "@/lib/api";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export function useStockOverview(ticker: string) {
  return useSWR(ticker ? `/stocks/${ticker}` : null, fetcher, { refreshInterval: 60000 });
}

export function usePriceHistory(ticker: string, period: string) {
  return useSWR(ticker ? `/stocks/${ticker}/history?period=${period}` : null, fetcher);
}

export function useFundamentals(ticker: string) {
  return useSWR(ticker ? `/stocks/${ticker}/fundamentals` : null, fetcher);
}

export function useNews(ticker: string) {
  return useSWR(ticker ? `/stocks/${ticker}/news` : null, fetcher);
}

export function useTechnicalIndicators(ticker: string) {
  return useSWR(ticker ? `/stocks/${ticker}/indicators` : null, fetcher);
}
