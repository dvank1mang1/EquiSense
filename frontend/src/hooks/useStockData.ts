import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { normalizeJsonValue } from "@/types/api";

const fetcher = (url: string) => apiGet<any>(url, undefined, normalizeJsonValue as (data: unknown) => any);

/** Новости ходят во внешние API; бэкенд режет таймаут ~12s — даём запас до axios. */
const newsFetcher = (url: string) =>
  apiGet<any>(url, { timeout: 25_000 }, normalizeJsonValue as (data: unknown) => any);

export function useStockOverview(ticker: string) {
  return useSWR(ticker ? `/stocks/${ticker}` : null, fetcher, { refreshInterval: 60000 });
}

export function usePriceHistory(ticker: string, period: string) {
  const qs = new URLSearchParams({ period }).toString();
  return useSWR(ticker ? `/stocks/${ticker}/history?${qs}` : null, fetcher);
}

export function useFundamentals(ticker: string) {
  return useSWR(ticker ? `/stocks/${ticker}/fundamentals` : null, fetcher);
}

export function useNews(ticker: string | null, options?: { limit?: number }) {
  const lim = options?.limit;
  const qs =
    lim != null && lim >= 1 && lim <= 100
      ? `?limit=${encodeURIComponent(String(lim))}`
      : "";
  return useSWR(ticker ? `/stocks/${ticker}/news${qs}` : null, newsFetcher, {
    dedupingInterval: 60_000,
    revalidateOnFocus: false,
  });
}

export function useTechnicalIndicators(ticker: string) {
  return useSWR(ticker ? `/stocks/${ticker}/indicators` : null, fetcher);
}
