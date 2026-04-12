/** Matches backend JSON error envelope (main.HTTPException handler). */
export type ApiErrorBody = {
  code: string;
  message: string;
  request_id: string;
};

export type ApiErrorEnvelope = { error: ApiErrorBody };

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function parseApiErrorBody(data: unknown): ApiErrorBody | null {
  if (!isRecord(data)) return null;
  const err = (data as ApiErrorEnvelope).error;
  if (!isRecord(err)) return null;
  const { code, message, request_id } = err as Record<string, unknown>;
  if (typeof code !== "string" || typeof message !== "string" || typeof request_id !== "string") {
    return null;
  }
  return { code, message, request_id };
}

/**
 * Parses unknown payloads into plain JSON-like structures to keep the
 * API boundary predictable for consumers.
 */
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export function normalizeJsonValue(value: unknown): JsonValue {
  if (value === null) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeJsonValue(item));
  }
  if (isRecord(value)) {
    const normalized: { [key: string]: JsonValue } = {};
    for (const [key, item] of Object.entries(value)) {
      normalized[key] = normalizeJsonValue(item);
    }
    return normalized;
  }
  throw new Error("Unexpected API response payload type.");
}
