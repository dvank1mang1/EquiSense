import axios, { isAxiosError, type AxiosError } from "axios";
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
