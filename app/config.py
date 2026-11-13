"""Centralized, validated configuration for Support Knowledge Copilot.

Uses Pydantic Settings for type-safe environment variable parsing, validation,
and automatic loading from the local ``.env`` file.
"""

from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase credentials & database
    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_key: str = Field(default="", validation_alias="SUPABASE_KEY")
    supabase_service_key: str = Field(
        default="", validation_alias="SUPABASE_SERVICE_KEY"
    )
    supabase_storage_bucket: str = Field(
        default="documents", validation_alias="SUPABASE_STORAGE_BUCKET"
    )

    # Qdrant Vector Store
    qdrant_url: str = Field(default="", validation_alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", validation_alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(
        default="support_chunks", validation_alias="QDRANT_COLLECTION"
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias="EMBEDDING_MODEL",
    )

    # DeepSeek LLM
    deepseek_api_key: str = Field(
        default="", validation_alias="DEEPSEEK_API_KEY"
    )
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias="DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias="DEEPSEEK_MODEL",
    )

    # Retrieval & Pipeline Strategy
    retrieval_strategy: str = Field(
        default="hybrid",
        validation_alias="RETRIEVAL_STRATEGY",
    )
    rrf_k: int = Field(default=60, validation_alias="RRF_K")
    top_k: int = Field(default=5, validation_alias="TOP_K")
    candidate_k: int = Field(default=20, validation_alias="CANDIDATE_K")

    # Cache Settings
    cache_ttl_seconds: int = Field(
        default=300, validation_alias="CACHE_TTL_SECONDS"
    )
    cache_max_size: int = Field(
        default=256, validation_alias="CACHE_MAX_SIZE"
    )

    # CORS configuration
    cors_origins: Union[List[str], str] = Field(
        default=["http://localhost:8501", "http://127.0.0.1:8501"],
        validation_alias="CORS_ORIGINS",
    )

    # Rate limiting
    rate_limit_per_minute: int = Field(
        default=30, validation_alias="RATE_LIMIT_PER_MINUTE"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
