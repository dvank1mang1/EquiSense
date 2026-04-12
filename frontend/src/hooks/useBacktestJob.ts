import useSWR from "swr";
import { apiGet, apiPost, getClientError } from "@/lib/api";
import { normalizeJsonValue, type JsonValue } from "@/types/api";

type BacktestJobRunBody = {
  model: string;
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
};

type BacktestJobStatus =
  | { job_id: string; status: "queued" | "running" }
  | { job_id: string; status: "completed"; result: JsonValue }
  | { job_id: string; status: "failed"; error?: string };

type BacktestPreflight = {
  ticker: string;
  ready: boolean;
  has_cached_ohlcv: boolean;
  /** True если есть technical.parquet (из него собирается combined для модели). */
  has_combined_features: boolean;
  has_processed_technical: boolean;
  reason: string;
};

const RUN_ENDPOINT = (ticker: string) => `/backtesting/${ticker}/run`;
const JOB_ENDPOINT = (jobId: string) => `/backtesting/jobs/${jobId}`;
const PREFLIGHT_ENDPOINT = (ticker: string) => `/backtesting/${ticker}/preflight`;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseStartBacktestJobResponse(data: unknown): { job_id: string; status: string } {
  if (!isRecord(data) || typeof data.job_id !== "string" || typeof data.status !== "string") {
    throw new Error("Invalid backtest job creation response.");
  }
  return { job_id: data.job_id, status: data.status };
}

function parseBacktestJobStatus(data: unknown): BacktestJobStatus {
  if (!isRecord(data) || typeof data.job_id !== "string" || typeof data.status !== "string") {
    throw new Error("Invalid backtest job status payload.");
  }

  if (data.status === "queued" || data.status === "running") {
    return { job_id: data.job_id, status: data.status };
  }

  if (data.status === "completed") {
    return {
      job_id: data.job_id,
      status: "completed",
      result: normalizeJsonValue(data.result),
    };
  }

  if (data.status === "failed") {
    return {
      job_id: data.job_id,
      status: "failed",
      error: typeof data.error === "string" ? data.error : undefined,
    };
  }

  throw new Error(`Unknown backtest job status: ${data.status}`);
}

function parseBacktestPreflight(data: unknown): BacktestPreflight {
  if (!isRecord(data)) {
    throw new Error("Invalid backtest preflight payload.");
  }
  const {
    ticker,
    ready,
    has_cached_ohlcv,
    has_combined_features,
    has_processed_technical,
    reason,
  } = data as Record<string, unknown>;

  if (
    typeof ticker !== "string" ||
    typeof ready !== "boolean" ||
    typeof has_cached_ohlcv !== "boolean" ||
    typeof has_combined_features !== "boolean" ||
    typeof reason !== "string"
  ) {
    throw new Error("Invalid backtest preflight payload.");
  }

  const hpt =
    typeof has_processed_technical === "boolean" ? has_processed_technical : has_combined_features;

  return {
    ticker,
    ready,
    has_cached_ohlcv,
    has_combined_features,
    has_processed_technical: hpt,
    reason,
  };
}

export async function startBacktestJob(ticker: string, body: BacktestJobRunBody) {
  return apiPost<{ job_id: string; status: string }>(
    RUN_ENDPOINT(ticker),
    body,
    undefined,
    parseStartBacktestJobResponse
  );
}

export function useBacktestJob(jobId: string | null) {
  return useSWR<BacktestJobStatus>(
    jobId ? JOB_ENDPOINT(jobId) : null,
    (url: string) => apiGet<BacktestJobStatus>(url, undefined, parseBacktestJobStatus),
    {
      refreshInterval: (latestData) => {
        if (!latestData) return 1500;
        if (latestData.status === "queued" || latestData.status === "running") {
          return 2000;
        }
        return 0;
      },
      keepPreviousData: true,
      dedupingInterval: 1000,
      revalidateOnFocus: true,
      shouldRetryOnError: (error) => {
        const normalized = getClientError(error);
        return normalized.retryable && normalized.kind !== "cancelled";
      },
      errorRetryInterval: 3000,
      errorRetryCount: 4,
    }
  );
}

export function useBacktestPreflight(ticker: string | null) {
  return useSWR<BacktestPreflight>(
    ticker ? PREFLIGHT_ENDPOINT(ticker) : null,
    (url: string) => apiGet<BacktestPreflight>(url, undefined, parseBacktestPreflight),
    {
      refreshInterval: 15000,
      revalidateOnFocus: true,
      dedupingInterval: 1000,
      shouldRetryOnError: (error) => getClientError(error).retryable,
      errorRetryCount: 3,
    }
  );
}

