import useSWR from "swr";
import { api } from "@/lib/api";

type BacktestJobRunBody = {
  model: string;
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
};

type BacktestJobStatus =
  | { job_id: string; status: "queued" | "running" }
  | { job_id: string; status: "completed"; result: any }
  | { job_id: string; status: "failed"; error?: string };

type BacktestPreflight = {
  ticker: string;
  ready: boolean;
  has_cached_ohlcv: boolean;
  has_combined_features: boolean;
  reason: string;
};

const RUN_ENDPOINT = (ticker: string) => `/backtesting/${ticker}/run`;
const JOB_ENDPOINT = (jobId: string) => `/backtesting/jobs/${jobId}`;
const PREFLIGHT_ENDPOINT = (ticker: string) => `/backtesting/${ticker}/preflight`;

export async function startBacktestJob(ticker: string, body: BacktestJobRunBody) {
  const resp = await api.post(RUN_ENDPOINT(ticker), body);
  return resp.data as { job_id: string; status: string };
}

export function useBacktestJob(jobId: string | null) {
  return useSWR<BacktestJobStatus>(
    jobId ? JOB_ENDPOINT(jobId) : null,
    (url: string) => api.get(url).then((r) => r.data),
    {
      refreshInterval: (latestData) => {
        if (!latestData) return 0;
        if (latestData.status === "queued" || latestData.status === "running") {
          return 2000;
        }
        return 0;
      },
    }
  );
}

export function useBacktestPreflight(ticker: string | null) {
  return useSWR<BacktestPreflight>(
    ticker ? PREFLIGHT_ENDPOINT(ticker) : null,
    (url: string) => api.get(url).then((r) => r.data),
    {
      refreshInterval: 15000,
      revalidateOnFocus: true,
    }
  );
}

