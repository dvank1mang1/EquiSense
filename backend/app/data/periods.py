"""Map UI period presets to approximate row counts (trading days)."""

import pandas as pd

PERIOD_ROWS: dict[str, int] = {
    "1m": 22,
    "3m": 66,
    "6m": 126,
    "1y": 252,
    "2y": 504,
    "max": 10**9,
}


def ohlcv_tail_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    if df.empty:
        return df
    n = PERIOD_ROWS.get(period, PERIOD_ROWS["1y"])
    return df.tail(n).reset_index(drop=True)
