"""FastAPI dependency factories — wire concrete adapters to Protocol-typed services."""

from fastapi import Depends, Request

from app.contracts.data_providers import (
    FundamentalDataProvider,
    MarketDataProvider,
    NewsDataProvider,
)
from app.contracts.features import FeatureStorePort
from app.contracts.jobs import JobStore
from app.core.config import settings
from app.core.database import engine
from app.data.fundamental_data import FundamentalDataClient
from app.data.market_data import MarketDataClient
from app.data.news_data import NewsDataClient
from app.etl.pipeline import RawToProcessedETL
from app.features.feature_store import FeatureStore
from app.jobs.batch_refresh import BatchRefreshOrchestrator
from app.jobs.store import FileJobStore, PostgresJobStore, ResilientJobStore
from app.services.backtesting_service import BacktestingService
from app.services.experiment_store import (
    ExperimentStore,
    InMemoryExperimentStore,
    PostgresExperimentStore,
    ResilientExperimentStore,
)
from app.services.lifecycle_store import (
    InMemoryLifecycleStore,
    LifecycleStore,
    PostgresLifecycleStore,
    ResilientLifecycleStore,
)
from app.services.prediction_service import PredictionService
from app.services.training_service import TrainingService, get_training_registry

_memory_experiment_store = InMemoryExperimentStore()
_experiment_store: ExperimentStore
if settings.experiment_store_backend.lower() == "postgres":
    _experiment_store = ResilientExperimentStore(
        primary=PostgresExperimentStore(engine=engine),
        fallback=_memory_experiment_store,
    )
else:
    _experiment_store = _memory_experiment_store

_file_job_store = FileJobStore()
_job_store: JobStore
if settings.job_store_backend.lower() == "postgres":
    _job_store = ResilientJobStore(primary=PostgresJobStore(), fallback=_file_job_store)
else:
    _job_store = _file_job_store

_memory_lifecycle_store = InMemoryLifecycleStore()
_lifecycle_store: LifecycleStore
if settings.lifecycle_store_backend.lower() == "postgres":
    _lifecycle_store = ResilientLifecycleStore(
        primary=PostgresLifecycleStore(engine=engine),
        fallback=_memory_lifecycle_store,
    )
else:
    _lifecycle_store = _memory_lifecycle_store


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


def get_backtesting_service(request: Request) -> BacktestingService:
    return BacktestingService(
        market=MarketDataClient(http=get_http_client(request)),
        features=FeatureStore(),
    )


def get_training_service() -> TrainingService:
    return TrainingService(
        features=FeatureStore(),
        registry=get_training_registry(),
        experiment_store=_experiment_store,
        lifecycle=_lifecycle_store,
    )


def get_etl_runner() -> RawToProcessedETL:
    return RawToProcessedETL()


def get_job_store() -> JobStore:
    return _job_store


def get_batch_refresh_orchestrator(request: Request) -> BatchRefreshOrchestrator:
    return BatchRefreshOrchestrator(
        market=MarketDataClient(http=get_http_client(request)),
        fundamentals=FundamentalDataClient(http=get_http_client(request)),
        etl_runner=get_etl_runner(),
        job_store=get_job_store(),
    )
