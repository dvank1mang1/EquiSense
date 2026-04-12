/** Числа для карточки «Фундаментал» из ответа API (snake_case + поля Alpha Vantage). */

export type FundamentalMetrics = {
  pe_ratio?: number;
  eps?: number;
  revenue_growth?: number;
  roe?: number;
  debt_to_equity?: number;
  dividend_yield?: number;
};

function toFiniteNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const t = value.replace(/[%$,]/g, "").trim();
    if (!t || t === "—") return undefined;
    const n = Number(t);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

function normalizeDividendYield(raw: unknown): number | undefined {
  const v = toFiniteNumber(raw);
  if (v == null) return undefined;
  if (v > 1 && v <= 100) return v / 100;
  return v;
}

export function extractFundamentalMetrics(raw: Record<string, unknown>): FundamentalMetrics {
  const pe =
    toFiniteNumber(raw.pe_ratio) ??
    toFiniteNumber(raw.PERatio) ??
    toFiniteNumber(raw.PERatioTTM) ??
    toFiniteNumber(raw.PE);
  const eps =
    toFiniteNumber(raw.eps) ?? toFiniteNumber(raw.EPS) ?? toFiniteNumber(raw.DilutedEPS);
  const revenue_growth =
    toFiniteNumber(raw.revenue_growth) ??
    toFiniteNumber(raw.QuarterlyRevenueGrowthYOY) ??
    toFiniteNumber(raw.RevenueGrowthYOY) ??
    toFiniteNumber(raw.RevenueGrowth);
  const roe =
    toFiniteNumber(raw.roe) ??
    toFiniteNumber(raw.ReturnOnEquityTTM) ??
    toFiniteNumber(raw.ReturnOnEquity) ??
    toFiniteNumber(raw.ROE);
  const debt_to_equity =
    toFiniteNumber(raw.debt_to_equity) ??
    toFiniteNumber(raw.DebtToEquityRatio) ??
    toFiniteNumber(raw.DebtToEquity) ??
    toFiniteNumber(raw.QuarterlyDebtToEquity);

  let dividend_yield = normalizeDividendYield(raw.dividend_yield);
  if (dividend_yield == null) {
    dividend_yield = normalizeDividendYield(
      raw.DividendYield ?? raw.TrailingAnnualDividendYield ?? raw.dividendYield
    );
  }

  return {
    pe_ratio: pe,
    eps,
    revenue_growth,
    roe,
    debt_to_equity,
    dividend_yield,
  };
}
