import { describe, expect, it } from "vitest";
import { normalizeTicker } from "./ticker";

describe("normalizeTicker", () => {
  it("accepts common symbols", () => {
    expect(normalizeTicker(" aapl ")).toBe("AAPL");
    expect(normalizeTicker("BRK.B")).toBe("BRK.B");
    expect(normalizeTicker("BF-B")).toBe("BF-B");
  });

  it("rejects invalid input", () => {
    expect(normalizeTicker("")).toBeNull();
    expect(normalizeTicker("../etc/passwd")).toBeNull();
    expect(normalizeTicker("A".repeat(20))).toBeNull();
    expect(normalizeTicker("BAD TICKER")).toBeNull();
  });
});
