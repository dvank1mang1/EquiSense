import { describe, expect, it } from "vitest";
import { normalizeJsonValue, parseApiErrorBody } from "./api";

describe("parseApiErrorBody", () => {
  it("parses valid envelope", () => {
    expect(
      parseApiErrorBody({
        error: { code: "http_404", message: "nope", request_id: "rid-1" },
      })
    ).toEqual({ code: "http_404", message: "nope", request_id: "rid-1" });
  });

  it("returns null for malformed payloads", () => {
    expect(parseApiErrorBody(null)).toBeNull();
    expect(parseApiErrorBody({})).toBeNull();
    expect(parseApiErrorBody({ error: {} })).toBeNull();
    expect(parseApiErrorBody({ error: { code: 1, message: "x", request_id: "r" } })).toBeNull();
  });
});

describe("normalizeJsonValue", () => {
  it("normalizes primitives and nested structures", () => {
    expect(normalizeJsonValue(null)).toBeNull();
    expect(normalizeJsonValue("x")).toBe("x");
    expect(normalizeJsonValue(1.5)).toBe(1.5);
    expect(normalizeJsonValue(true)).toBe(true);
    expect(normalizeJsonValue([1, { a: "b" }])).toEqual([1, { a: "b" }]);
  });

  it("rejects unsupported types", () => {
    expect(() => normalizeJsonValue(undefined)).toThrow();
    expect(() => normalizeJsonValue(BigInt(1))).toThrow();
    expect(() => normalizeJsonValue(Symbol("s"))).toThrow();
  });
});
