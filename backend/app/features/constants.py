"""Single source of truth for model feature names (used by FE, FeatureStore, ML)."""

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
