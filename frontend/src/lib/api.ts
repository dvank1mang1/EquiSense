import axios, { isAxiosError, type AxiosError, type AxiosRequestConfig } from "axios";
import { parseApiErrorBody, type ApiErrorBody } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `req_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
}

export const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const id = newRequestId();
  config.headers.set("X-Request-ID", id);
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const clientError = toApiClientError(error);
    (error as AxiosError & { clientError: ApiClientError }).clientError = clientError;

    const apiError = parseApiErrorBody(error.response?.data);
    if (apiError) {
      (error as AxiosError & { apiError: ApiErrorBody }).apiError = apiError;
      const rid = error.response?.headers?.["x-request-id"];
      console.error(
        "API Error:",
        apiError.code,
        apiError.message,
        `[request_id=${apiError.request_id}]`,
        rid ? `(header ${rid})` : ""
      );
    } else {
      console.error("API Error:", error.response?.data ?? error.message);
    }
    return Promise.reject(error);
  }
);

export function getApiError(error: unknown): ApiErrorBody | null {
  if (!isAxiosError(error)) return null;
  const extended = error as AxiosError & { apiError?: ApiErrorBody };
  if (extended.apiError) return extended.apiError;
  return parseApiErrorBody(error.response?.data);
}

export type ApiClientErrorKind = "api" | "network" | "timeout" | "cancelled" | "unknown";

export type ApiClientError = {
  kind: ApiClientErrorKind;
  message: string;
  status?: number;
  requestId?: string;
  code?: string;
  retryable: boolean;
  cause: unknown;
};

export function toApiClientError(error: unknown): ApiClientError {
  if (!isAxiosError(error)) {
    return {
      kind: "unknown",
      message: "Unexpected error while processing request.",
      retryable: false,
      cause: error,
    };
  }

  const parsedApiError = parseApiErrorBody(error.response?.data);
  if (parsedApiError) {
    return {
      kind: "api",
      message: parsedApiError.message,
      status: error.response?.status,
      requestId: parsedApiError.request_id,
      code: parsedApiError.code,
      retryable: error.response ? error.response.status >= 500 : false,
      cause: error,
    };
  }

  if (error.code === "ERR_CANCELED") {
    return {
      kind: "cancelled",
      message: "Request was cancelled.",
      retryable: true,
      cause: error,
    };
  }

  if (error.code === "ECONNABORTED") {
    return {
      kind: "timeout",
      message: "Request timed out.",
      status: error.response?.status,
      retryable: true,
      cause: error,
    };
  }

  if (!error.response) {
    return {
      kind: "network",
      message: "Network error while contacting backend.",
      retryable: true,
      cause: error,
    };
  }

  return {
    kind: "unknown",
    message: error.message || "Request failed.",
    status: error.response.status,
    retryable: error.response.status >= 500,
    cause: error,
  };
}

export function getClientError(error: unknown): ApiClientError {
  if (isAxiosError(error)) {
    const extended = error as AxiosError & { clientError?: ApiClientError };
    if (extended.clientError) return extended.clientError;
  }
  return toApiClientError(error);
}

export async function apiGet<T = unknown>(
  url: string,
  config?: AxiosRequestConfig,
  normalize?: (data: unknown) => T
): Promise<T> {
  const response = await api.get<unknown>(url, config);
  return normalize ? normalize(response.data) : (response.data as T);
}

export async function apiPost<T = unknown>(
  url: string,
  payload?: unknown,
  config?: AxiosRequestConfig,
  normalize?: (data: unknown) => T
): Promise<T> {
  const response = await api.post<unknown>(url, payload, config);
  return normalize ? normalize(response.data) : (response.data as T);
}
