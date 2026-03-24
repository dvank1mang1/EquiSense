from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )

    # App
    app_name: str = "EquiSense API"
    debug: bool = False
    secret_key: str = "change_this_in_production"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "equisense"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    experiment_store_backend: str = "memory"
    lifecycle_store_backend: str = "memory"
    job_store_backend: str = "file"
    job_queue_backend: str = "memory"
    job_queue_stale_after_sec: int = 300
    worker_heartbeat_sec: float = 5.0
    job_queue_max_attempts: int = 3

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Data APIs
    alpha_vantage_api_key: str = ""
    finnhub_api_key: str = ""
    news_api_key: str = ""
    # Alpha Vantage free tier ~5 calls/min — pace all AV endpoints with one limiter
    alpha_vantage_min_interval_sec: float = 12.0
    ohlcv_parquet_cache_max_age_sec: int = 86400
    fundamentals_json_cache_max_age_sec: int = 604800
    quote_json_cache_max_age_sec: int = 120

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # ML
    model_dir: str = "data/models"
    random_seed: int = 42

    # CORS
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
