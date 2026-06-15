from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRETS = {
    "CHANGE_ME_IN_PRODUCTION",
    "CHANGE_ME_IN_PRODUCTION_use_openssl_rand_hex_64",
    "secret",
    "changeme",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    ENV: Literal["local", "development", "test", "qa", "uat", "production"] = "development"
    APP_NAME: str = "Solidcare V2"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://solidcare:solidcare@localhost:5432/solidcare_dev"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis (optional — disable for minimum-cost Azure demo deployments)
    REDIS_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # JWT Auth
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Azure Storage
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER_NAME: str = "solidcare-documents"
    AZURE_STORAGE_BLOB_URL_EXPIRY_HOURS: int = 1
    AZURE_KEY_VAULT_URL: str = ""
    USE_KEY_VAULT: bool = False

    # Email
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = "noreply@solidcare.health"
    EMAIL_FROM_NAME: str = "Solidcare Health"

    # SMS
    MSG91_AUTH_KEY: str = ""
    MSG91_SENDER_ID: str = "SOLID"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10

    # Observability
    APPLICATIONINSIGHTS_CONNECTION_STRING: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @model_validator(mode="after")
    def validate_secrets_in_production(self) -> "Settings":
        if self.ENV == "production":
            if self.JWT_SECRET_KEY in _INSECURE_SECRETS or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a secure random value in production. "
                    "Generate one with: openssl rand -hex 64"
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.ENV in ("local", "development", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
