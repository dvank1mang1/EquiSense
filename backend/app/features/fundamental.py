import math
import re
from typing import Any

import pandas as pd


def _parse_dividend_yield(raw: Any) -> float | None:
    """Доля (0.02 = 2%). Alpha Vantage часто отдаёт долю; встречается и процент > 1."""
    v = _parse_float(raw)
    if v is None:
        return None
    if v > 1.0:
        return v / 100.0
    return v


def _parse_float(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, int | float):
        if isinstance(raw, float) and (math.isnan(raw) or math.isinf(raw)):
            return None
        return float(raw)
    s = str(raw).strip()
    if s in ("", "None", "-", "N/A"):
        return None
    s = re.sub(r"[%$,]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


class FundamentalFeatureEngineer:
    """
    Формирует фундаментальные признаки из Alpha Vantage OVERVIEW.
    """

    def compute(
        self, overview: dict, income_df: pd.DataFrame | None = None
    ) -> dict[str, float | None]:
        _ = income_df
        pe = _parse_float(
            overview.get("PERatio") or overview.get("PERatioTTM") or overview.get("PE")
        )
        eps = _parse_float(overview.get("EPS") or overview.get("DilutedEPS"))
        rev_g = _parse_float(
            overview.get("QuarterlyRevenueGrowthYOY")
            or overview.get("RevenueGrowthYOY")
            or overview.get("RevenueGrowth")
        )
        roe = _parse_float(
            overview.get("ReturnOnEquityTTM")
            or overview.get("ReturnOnEquity")
            or overview.get("ROE")
        )
        de = _parse_float(
            overview.get("DebtToEquityRatio")
            or overview.get("QuarterlyDebtToEquity")
            or overview.get("DebtToEquity")
        )
        dy = _parse_dividend_yield(
            overview.get("DividendYield")
            or overview.get("TrailingAnnualDividendYield")
            or overview.get("dividendYield")
        )

        return {
            "pe_ratio": pe,
            "eps": eps,
            "revenue_growth": rev_g,
            "roe": roe,
            "debt_to_equity": de,
            "dividend_yield": dy,
        }

    def normalize(self, features: dict, reference: dict) -> dict:
        """Заглушка для нормализации относительно рыночных медиан (позже)."""
        _ = reference
        return dict(features)


def _is_blank_field(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() in ("", "N/A", "-", "None"):
        return True
    return False


def _core_fundamentals_all_missing(metrics: dict[str, float | None]) -> bool:
    """Все основные мультипликаторы пусты (типичный «тонкий» JSON из download-скрипта)."""
    core = ("pe_ratio", "eps", "revenue_growth", "roe", "debt_to_equity")
    return all(metrics.get(k) is None for k in core)


def enrich_overview_for_ui(overview: dict[str, Any]) -> dict[str, Any]:
    """
    Поверх сырого Alpha Vantage OVERVIEW добавляет pe_ratio, eps, … для фронтенда.
    Если в кэше только Symbol/Name, один раз подмешивает yfinance (пакет уже в проекте).
    """
    if "_error" in overview:
        return overview
    out = dict(overview)
    metrics = FundamentalFeatureEngineer().compute(out)

    if _core_fundamentals_all_missing(metrics):
        sym = str(out.get("Symbol") or out.get("symbol") or "").strip().upper()
        if sym:
            from app.data.yfinance_overview import yfinance_av_overview_patch

            patch = yfinance_av_overview_patch(sym)
            for k, v in patch.items():
                if _is_blank_field(out.get(k)) and not _is_blank_field(v):
                    out[k] = v
            metrics = FundamentalFeatureEngineer().compute(out)

    for key, val in metrics.items():
        if val is None:
            continue
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            continue
        out[key] = val
    return out
