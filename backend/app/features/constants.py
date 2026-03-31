TECHNICAL_FEATURES = [
    "returns",
    "volatility",
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "sma_20",
    "sma_50",
    "sma_200",
    "bb_upper",
    "bb_lower",
    "bb_width",
    "momentum",
]

FUNDAMENTAL_FEATURES = [
    "pe_ratio",
    "eps",
    "revenue_growth",
    "roe",
    "debt_to_equity",
]

SENTIMENT_FEATURES = [
    "sentiment_score",
    "news_count",
    "positive_ratio",
    "negative_ratio",
    "sentiment_momentum",
]

LAG_FEATURES = [
    "returns_lag1",
    "returns_lag2",
    "returns_lag3",
    "returns_lag5",
    "volatility_lag5",
    "rsi_lag3",
    "volume_change",
    "volume_lag1",
]

PRICE_FEATURES = [
    "returns_3d",
    "returns_10d",
    "returns_20d",
    "dist_52w_high",
    "dist_52w_low",
    "volume_ratio",
    "obv_change",
    "bb_pct",
]

SECTOR_FEATURES = [
    "ret1d_vs_sector",   # дневной return акции минус return её сектора
    "ret5d_vs_sector",   # 5d trailing return акции минус сектора
    "sector_ret1d",      # дневной return сектора (контекст рынка)
    "sector_vol5d",      # 5d волатильность сектора
    "sector_rsi",        # RSI сектора (перекупленность/перепроданность сектора)
]

MACRO_FEATURES = [
    "spy_return",       # дневной доход S&P 500
    "spy_vol_5d",       # 5d волатильность SPY
    "vix_level",        # уровень VIX
    "vix_change",       # изменение VIX за день
    "qqq_return",       # доход NASDAQ-100
    "tlt_return",       # доход длинных облигаций (risk-off)
    "gld_return",       # доход золота (safe-haven)
    "spy_qqq_spread",   # спред SPY-QQQ (ротация growth/value)
    "vix_spy_ratio",    # VIX / |SPY return| (нормированный страх)
]
