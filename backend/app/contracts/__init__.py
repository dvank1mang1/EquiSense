"""
Architecture: hexagonal-style ports.

- `contracts.*`: Protocols (what the app needs).
- `data`, `features`, `models`, `backtesting`: adapters (how it is done).

Routers should call application services; services depend on Protocols; wiring via `app.services.dependencies`.
"""

from app.contracts.backtesting import BacktestRunner
from app.contracts.data_providers import (
    FundamentalDataProvider,
    MarketDataProvider,
    NewsDataProvider,
)
from app.contracts.features import FeatureStorePort
from app.contracts.ml import TabularEquityModel

__all__ = [
    "BacktestRunner",
    "FeatureStorePort",
    "FundamentalDataProvider",
    "MarketDataProvider",
    "NewsDataProvider",
    "TabularEquityModel",
]
