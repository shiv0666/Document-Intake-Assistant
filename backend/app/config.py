from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )

    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="qwen/qwen3.8-27b", alias="GROQ_MODEL")
    groq_fallback_model: Optional[str] = Field(default=None, alias="GROQ_FALLBACK_MODEL")
    groq_max_rate_limit_wait_seconds: int = Field(default=30, ge=0, le=60, alias="GROQ_MAX_RATE_LIMIT_WAIT_SECONDS")
    mongodb_uri: Optional[str] = Field(default=None, alias="MONGODB_URI")
    frontend_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        alias="FRONTEND_ORIGINS",
    )
    app_name: str = "document-intake-assistant"


@lru_cache
def get_settings() -> Settings:
    return Settings()
