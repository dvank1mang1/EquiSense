"""FastAPI dependency factories — wire concrete adapters to Protocol-typed services."""

from fastapi import Depends, Request

from app.contracts.data_providers import (
    FundamentalDataProvider,
    MarketDataProvider,
    NewsDataProvider,
)
from app.contracts.features import FeatureStorePort
from app.data.fundamental_data import FundamentalDataClient
from app.data.market_data import MarketDataClient
from app.data.news_data import NewsDataClient
from app.features.feature_store import FeatureStore
from app.services.prediction_service import PredictionService


def get_http_client(request: Request):
    return request.app.state.http_client


def get_market_data_provider(request: Request) -> MarketDataProvider:
    return MarketDataClient(http=get_http_client(request))


def get_fundamental_data_provider(request: Request) -> FundamentalDataProvider:
    return FundamentalDataClient(http=get_http_client(request))


def get_news_data_provider(request: Request) -> NewsDataProvider:
    return NewsDataClient(http=get_http_client(request))


def get_feature_store() -> FeatureStorePort:
    return FeatureStore()


def get_prediction_service(
    request: Request,
    features: FeatureStorePort = Depends(get_feature_store),
) -> PredictionService:
    return PredictionService(
        market=MarketDataClient(http=get_http_client(request)),
        features=features,
    )
