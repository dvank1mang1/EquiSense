from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → каталог backend
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent


def _env_file_chain() -> tuple[Path | str, ...]:
    """
    Сначала .env у корня репозитория (как у docker compose), затем backend/.env.
    В контейнере корень репо обычно не смонтирован — тогда остаётся только backend/.env или cwd .env.
    """
    files: list[Path] = []
    repo_env = _REPO_ROOT / ".env"
    if repo_env.is_file():
        files.append(repo_env)
    back_env = _BACKEND_DIR / ".env"
    if back_env.is_file():
        files.append(back_env)
    return tuple(files) if files else (".env",)


_ENV_FILES = _env_file_chain()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        protected_namespaces=("settings_",),
        # Корневой .env (docker-compose) задаёт DATABASE_URL, NEXT_PUBLIC_*, Grafana — не поля этого класса.
        extra="ignore",
    )

    # App
    app_name: str = "EquiSense API"
    # Semver-ish release (overridable in deploy: APP_VERSION=1.2.3)
    app_version: str = "0.1.0"
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
    # Тональность FinBERT для GET /stocks/.../news (первый запрос грузит модель; отключить: false)
    news_finbert_enabled: bool = True
    # Alpha Vantage free tier ~5 calls/min — pace all AV endpoints with one limiter
    alpha_vantage_min_interval_sec: float = 12.0
    ohlcv_parquet_cache_max_age_sec: int = 86400
    fundamentals_json_cache_max_age_sec: int = 604800
    quote_json_cache_max_age_sec: int = 120
    backtest_allow_network_fallback: bool = False
    auto_promotion_min_roc_auc_delta: float = 0.005
    auto_promotion_max_brier_increase: float = 0.01
    auto_promotion_min_f1_delta: float = -0.02

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"

    # ML
    model_dir: str = "data/models"
    random_seed: int = 42
    # Time-ordered split: train [0, train_frac), val [train_frac, val_end), test [val_end, 1)
    training_split_train_fraction: float = Field(default=0.70, ge=0.05, le=0.95)
    training_split_val_end_fraction: float = Field(default=0.85, ge=0.10, le=0.99)
    training_min_rows: int = Field(default=60, ge=30, le=500_000)
    training_calibration_min_val_samples: int = Field(default=50, ge=10, le=100_000)

    @model_validator(mode="after")
    def _training_fractions_ordered(self) -> "Settings":
        if self.training_split_train_fraction >= self.training_split_val_end_fraction:
            raise ValueError(
                "training_split_train_fraction must be < training_split_val_end_fraction"
            )
        return self

    # FinBERT sentiment (ProsusAI/finbert) — inference only, no fine-tuning
    finbert_model_name: str = "ProsusAI/finbert"
    # auto | cpu | cuda
    finbert_device: str = "auto"
    finbert_batch_size: int = 16

    # CORS (include Docker frontend on 3002 when host :3000 is busy)
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
