"""Application configuration using Pydantic Settings.

All configuration is loaded from environment variables.
See .env.example for required variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ==========================================================================
    # API Keys
    # ==========================================================================
    groq_api_key: SecretStr = Field(description="Groq API key for LLM")
    deepgram_api_key: SecretStr = Field(description="Deepgram API key for STT")
    plivo_auth_id: str = Field(description="Plivo Auth ID")
    plivo_auth_token: SecretStr = Field(description="Plivo Auth Token")

    # ==========================================================================
    # Security Keys
    # ==========================================================================
    phone_encryption_key: SecretStr = Field(
        description="AES-256-GCM key for encrypting phone numbers (64 hex chars)"
    )
    phone_hash_pepper: SecretStr = Field(
        description="HMAC-SHA256 pepper for hashing phone numbers (64 hex chars)"
    )
    admin_password_hash: str = Field(description="bcrypt hash of admin password")
    session_secret: SecretStr = Field(description="Secret for session management")

    # ==========================================================================
    # Database
    # ==========================================================================
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/vartalaap.db",
        description="SQLAlchemy async database URL",
    )

    # ==========================================================================
    # Redis
    # ==========================================================================
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis URL for arq task queue",
    )

    # ==========================================================================
    # Application
    # ==========================================================================
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Logging level"
    )
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Deployment environment"
    )

    # ==========================================================================
    # Feature Flags
    # ==========================================================================
    edge_tts_enabled: bool = Field(
        default=False,
        description="Enable Edge TTS as fallback (unofficial API, may be unreliable)",
    )

    # ==========================================================================
    # Derived Properties
    # ==========================================================================
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def redis_settings(self) -> dict:
        """Get Redis connection settings for arq."""
        from arq.connections import RedisSettings

        # Parse redis URL
        # Format: redis://[[username:]password@]host[:port][/database]
        url = self.redis_url
        if url.startswith("redis://"):
            url = url[8:]

        # Simple parsing for common case
        host = "localhost"
        port = 6379
        database = 0

        if "/" in url:
            url, db_str = url.rsplit("/", 1)
            database = int(db_str) if db_str else 0

        if ":" in url:
            parts = url.rsplit(":", 1)
            host = parts[0]
            port = int(parts[1])
        else:
            host = url

        return RedisSettings(host=host, port=port, database=database)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Use dependency injection in FastAPI:
        settings: Settings = Depends(get_settings)
    """
    return Settings()
