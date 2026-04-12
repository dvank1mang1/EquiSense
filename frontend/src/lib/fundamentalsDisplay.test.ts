import { describe, expect, it } from "vitest";
import { extractFundamentalMetrics } from "./fundamentalsDisplay";

describe("extractFundamentalMetrics", () => {
  it("reads snake_case from enriched API", () => {
    const m = extractFundamentalMetrics({
      Symbol: "T",
      pe_ratio: 12.5,
      eps: 2,
      revenue_growth: 0.08,
      roe: 0.15,
      debt_to_equity: 0.9,
      dividend_yield: 0.02,
    });
    expect(m.pe_ratio).toBe(12.5);
    expect(m.eps).toBe(2);
    expect(m.revenue_growth).toBe(0.08);
    expect(m.roe).toBe(0.15);
    expect(m.debt_to_equity).toBe(0.9);
    expect(m.dividend_yield).toBe(0.02);
  });

  it("falls back to Alpha Vantage string keys", () => {
    const m = extractFundamentalMetrics({
      PERatio: "28.5",
      EPS: "6.1",
      QuarterlyRevenueGrowthYOY: "0.05",
      ReturnOnEquityTTM: "0.2",
      DebtToEquityRatio: "1.1",
      DividendYield: "0.015",
    });
    expect(m.pe_ratio).toBe(28.5);
    expect(m.eps).toBe(6.1);
    expect(m.revenue_growth).toBe(0.05);
    expect(m.roe).toBe(0.2);
    expect(m.debt_to_equity).toBe(1.1);
    expect(m.dividend_yield).toBe(0.015);
  });

  it("normalizes dividend yield when API sends percent > 1", () => {
    expect(extractFundamentalMetrics({ DividendYield: "2.5" }).dividend_yield).toBe(0.025);
  });
});
