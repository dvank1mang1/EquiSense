import useSWR from "swr";
import { api } from "@/lib/api";

const fetcher = (url: string) => api.get(url).then((r) => r.data);

export function usePrediction(ticker: string, model: string) {
  return useSWR(
    ticker ? `/predictions/${ticker}?model=${model}` : null,
    fetcher,
    { refreshInterval: 300000 }
  );
}

export function useModelComparison(ticker: string) {
  return useSWR(ticker ? `/predictions/${ticker}/compare` : null, fetcher);
}

export function useShapExplanation(ticker: string, model: string) {
  return useSWR(
    ticker ? `/predictions/${ticker}/shap?model=${model}` : null,
    fetcher
  );
}
