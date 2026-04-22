import useSWR from "swr";
import { api } from "@/lib/api";

/** Six sequential predicts + feature build — default 30s axios often ECONNABORTED (shown as «сеть»). */
const PREDICTION_COMPARE_TIMEOUT_MS = 120_000;

const fetcher = (url: string) => api.get(url).then((r) => r.data);

const compareFetcher = (url: string) =>
  api.get(url, { timeout: PREDICTION_COMPARE_TIMEOUT_MS }).then((r) => r.data);

export function usePrediction(ticker: string, model: string) {
  return useSWR(
    ticker ? `/predictions/${ticker}?model=${model}` : null,
    fetcher,
    { refreshInterval: 300000 }
  );
}

export function useModelComparison(ticker: string) {
  return useSWR(ticker ? `/predictions/${ticker}/compare` : null, compareFetcher, {
    keepPreviousData: true,
  });
}

export function useShapExplanation(ticker: string, model: string) {
  return useSWR(
    ticker ? `/predictions/${ticker}/shap?model=${model}` : null,
    fetcher
  );
}
