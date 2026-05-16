from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default="sqlite:///./local.db", alias="DATABASE_URL")
    environment: str = Field(default="prod", alias="ENVIRONMENT")

    kalshi_base_url: str = Field(
        default="https://api.elections.kalshi.com/trade-api/v2", alias="KALSHI_BASE_URL"
    )
    kalshi_api_key: str | None = Field(default=None, alias="KALSHI_API_KEY")
    kalshi_private_key: str | None = Field(default=None, alias="KALSHI_PRIVATE_KEY")

    optic_odds_base_url: str = Field(default="https://api.opticodds.com/api/v3", alias="OPTIC_ODDS_BASE_URL")
    oddsjam_api_key: str | None = Field(default=None, alias="ODDSJAM_API_KEY")
    cors_origins_csv: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    discover_markets_interval_seconds: int = Field(default=900, alias="DISCOVER_MARKETS_INTERVAL_SECONDS")
    kalshi_orderbook_interval_seconds: int = Field(default=60, alias="KALSHI_ORDERBOOK_INTERVAL_SECONDS")
    sharp_odds_interval_seconds: int = Field(default=60, alias="SHARP_ODDS_INTERVAL_SECONDS")
    sharp_limits_interval_seconds: int = Field(default=300, alias="SHARP_LIMITS_INTERVAL_SECONDS")
    derived_metrics_interval_seconds: int = Field(default=60, alias="DERIVED_METRICS_INTERVAL_SECONDS")
    opportunity_scores_interval_seconds: int = Field(default=60, alias="OPPORTUNITY_SCORES_INTERVAL_SECONDS")
    kalshi_trades_interval_seconds: int = Field(default=60, alias="KALSHI_TRADES_INTERVAL_SECONDS")
    private_fills_interval_seconds: int = Field(default=300, alias="PRIVATE_FILLS_INTERVAL_SECONDS")
    feature_bucket_interval_seconds: int = Field(default=60, alias="FEATURE_BUCKET_INTERVAL_SECONDS")
    event_detection_interval_seconds: int = Field(default=60, alias="EVENT_DETECTION_INTERVAL_SECONDS")
    cleanup_interval_seconds: int = Field(default=86400, alias="CLEANUP_INTERVAL_SECONDS")
    kalshi_private_data_enabled: bool = Field(default=False, alias="KALSHI_PRIVATE_DATA_ENABLED")

    polling_leagues_csv: str = Field(default="mlb", alias="POLLING_LEAGUES")
    polling_markets_csv: str = Field(default="Moneyline,Run Line,Total Runs,1st Half Total Runs", alias="POLLING_MARKETS")
    kalshi_series_prefixes_csv: str = Field(
        default="KXMLBGAME,KXMLBSPREAD,KXMLBTOTAL,KXMLBF5TOTAL",
        alias="KALSHI_SERIES_PREFIXES",
    )
    sharp_books_csv: str = Field(default="Pinnacle,Circa Sports,BetOnline,Betcris", alias="SHARP_BOOKS")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://") and "+psycopg" not in value:
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def polling_leagues(self) -> list[str]:
        return split_csv(self.polling_leagues_csv)

    @property
    def polling_markets(self) -> list[str]:
        return split_csv(self.polling_markets_csv)

    @property
    def kalshi_series_prefixes(self) -> list[str]:
        return split_csv(self.kalshi_series_prefixes_csv)

    @property
    def sharp_books(self) -> list[str]:
        return split_csv(self.sharp_books_csv)

    @property
    def cors_origins(self) -> list[str]:
        return split_csv(self.cors_origins_csv)


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
