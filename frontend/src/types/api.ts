/** Matches backend JSON error envelope (main.HTTPException handler). */
export type ApiErrorBody = {
  code: string;
  message: string;
  request_id: string;
};

export type ApiErrorEnvelope = { error: ApiErrorBody };

export function parseApiErrorBody(data: unknown): ApiErrorBody | null {
  if (!data || typeof data !== "object") return null;
  const err = (data as ApiErrorEnvelope).error;
  if (!err || typeof err !== "object") return null;
  const { code, message, request_id } = err as Record<string, unknown>;
  if (typeof code !== "string" || typeof message !== "string" || typeof request_id !== "string") {
    return null;
  }
  return { code, message, request_id };
}
