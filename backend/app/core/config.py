"""
Core configuration using Pydantic BaseSettings.
Environment variables drive all configuration — no hardcoded secrets.
"""
import os
from functools import lru_cache
from typing import Optional

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    APP_NAME: str = "ArchPilot"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # API
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173","http://127.0.0.1:8000","http://localhost:3001","https://arch-pilot-2.onrender.com/"]

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL  ")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL")
    CACHE_TTL_SECONDS: int = 3600

    # GitHub
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_RAW_BASE: str = "https://raw.githubusercontent.com"
    GITHUB_MAX_FILE_SIZE_KB: int = 500
    GITHUB_MAX_FILES_PER_REPO: int = 2000

    # AI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    AI_MODEL: str = "gemini-2.5-flash"
    AI_MAX_TOKENS: int = 2048
    AI_TEMPERATURE: float = 0.3

    # Analysis
    MAX_GRAPH_NODES: int = 5000
    ANALYSIS_TIMEOUT_SECONDS: int = 300

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — instantiated once per process."""
    return Settings()


settings = get_settings()
