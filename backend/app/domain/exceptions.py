"""Domain-level errors — map to HTTP in API layer, not inside ML/data adapters."""


class EquiSenseError(Exception):
    """Base error for application/domain failures."""


class UnknownModelError(EquiSenseError):
    """Requested model_id is not registered."""


class ModelArtifactMissingError(EquiSenseError):
    """Trained weights or artifact not found on disk."""


class FeatureDataMissingError(EquiSenseError):
    """No processed features for ticker/slice (ingestion or FE not run)."""


class RawDataMissingError(EquiSenseError):
    """Expected raw Parquet/JSON under data/raw is missing."""


class DataProviderError(EquiSenseError):
    """Upstream data provider returned an error or unexpected payload."""


class DataProviderConfigError(EquiSenseError):
    """Missing API credentials or invalid local configuration for data access."""


class UpstreamRateLimitError(DataProviderError):
    """Vendor rate limit or quota message (e.g. Alpha Vantage free tier)."""
