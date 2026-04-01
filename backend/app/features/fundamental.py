import math
import re
from typing import Any

import pandas as pd


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

        return {
            "pe_ratio": pe,
            "eps": eps,
            "revenue_growth": rev_g,
            "roe": roe,
            "debt_to_equity": de,
        }

    def normalize(self, features: dict, reference: dict) -> dict:
        """Заглушка для нормализации относительно рыночных медиан (позже)."""
        _ = reference
        return dict(features)
