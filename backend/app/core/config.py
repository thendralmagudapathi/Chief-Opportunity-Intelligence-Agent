"""Application configuration.

All settings are environment-driven and validated at import time. Nested
sections use a double-underscore delimiter, e.g. ``DATABASE__POOL_SIZE``.

The production validator is deliberately strict: the application refuses to
start with a placeholder secret, debug mode, or a wildcard CORS origin outside
development (see docs/SECURITY_MODEL.md §4).
"""

from __future__ import annotations

import secrets
from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_PLACEHOLDER = "change-me-in-production"  # noqa: S105  (sentinel, rejected in prod)


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production_like(self) -> bool:
        return self in (Environment.STAGING, Environment.PRODUCTION)


class DatabaseSettings(BaseModel):
    """PostgreSQL connection and pooling.

    The URL must use an async driver (``postgresql+asyncpg`` or
    ``sqlite+aiosqlite``); the whole persistence layer is async.
    """

    url: str = "postgresql+asyncpg://oia:oia@localhost:5432/oia"
    echo: bool = False
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=20, ge=0, le=100)
    pool_timeout_s: int = Field(default=30, ge=1)
    pool_recycle_s: int = Field(default=1800, ge=60)
    connect_timeout_s: int = Field(default=10, ge=1)

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")

    @property
    def safe_url(self) -> str:
        """URL with credentials removed, safe to log."""
        if "@" not in self.url:
            return self.url
        scheme, _, rest = self.url.partition("://")
        return f"{scheme}://***@{rest.rpartition('@')[2]}"


class SecuritySettings(BaseModel):
    secret_key: SecretStr = SecretStr(DEV_SECRET_PLACEHOLDER)
    jwt_algorithm: Literal["HS256", "HS512"] = "HS256"
    access_token_ttl_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_ttl_days: int = Field(default=14, ge=1, le=90)
    password_min_length: int = Field(default=12, ge=8, le=128)

    # Argon2id parameters. Defaults follow OWASP's second recommended profile.
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost_kib: int = Field(default=65536, ge=8192)
    argon2_parallelism: int = Field(default=4, ge=1)

    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=120, ge=1)
    rate_limit_window_s: int = Field(default=60, ge=1)
    auth_rate_limit_requests: int = Field(default=10, ge=1)
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)


class CorsSettings(BaseModel):
    # Comma-separated rather than JSON so it is pleasant to set in a shell.
    allow_origins: str = "http://localhost:3000"
    allow_credentials: bool = True

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allow_origins.split(",") if o.strip()]


class RedisSettings(BaseModel):
    enabled: bool = False
    url: str = "redis://localhost:6379/0"
    cache_ttl_s: int = Field(default=3600, ge=1)


class StorageSettings(BaseModel):
    """Object storage for uploaded profile documents."""

    local_path: str = "./data/uploads"


class RagSettings(BaseModel):
    """Retrieval configuration.

    ``embedding_dim`` must match the dimension baked into the migration; it is
    asserted at startup rather than silently truncating vectors.
    """

    embedding_provider: Literal["ollama", "openai", "tei", "fake"] = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = Field(default=768, ge=64, le=4096)
    vector_store: Literal["pgvector", "qdrant", "chroma", "faiss"] = "pgvector"
    chunk_size_tokens: int = Field(default=512, ge=64)
    chunk_overlap_tokens: int = Field(default=64, ge=0)
    retrieval_top_k: int = Field(default=50, ge=1)
    rerank_top_n: int = Field(default=8, ge=1)
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_enabled: bool = True


class ModelSettings(BaseModel):
    """Model provider and task-class routing (see docs/ARCHITECTURE.md §8)."""

    provider: Literal["ollama", "vllm", "cloud", "fake"] = "ollama"
    base_url: str = "http://localhost:11434"
    api_key: SecretStr | None = None
    request_timeout_s: float = Field(default=120.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)

    model_small: str = "qwen2.5:3b-instruct"
    model_standard: str = "qwen2.5:7b-instruct"
    model_reasoning: str = "qwen2.5:14b-instruct"
    model_extraction: str = "qwen2.5:7b-instruct"

    def for_task(self, task_class: Literal["small", "standard", "reasoning", "extract"]) -> str:
        return {
            "small": self.model_small,
            "standard": self.model_standard,
            "reasoning": self.model_reasoning,
            "extract": self.model_extraction,
        }[task_class]


class AgentSettings(BaseModel):
    """Bounded-autonomy limits (see docs/AGENT_DESIGN.md §6)."""

    max_iterations: int = Field(default=3, ge=1, le=10)
    max_tool_calls_total: int = Field(default=60, ge=1)
    max_tool_calls_per_candidate: int = Field(default=6, ge=1)
    max_candidates_researched: int = Field(default=15, ge=1)
    max_wall_clock_s: int = Field(default=600, ge=10)
    max_cost_usd: float = Field(default=1.0, ge=0.0)
    confidence_floor: float = Field(default=0.35, ge=0.0, le=1.0)


class EgressSettings(BaseModel):
    """Outbound fetch limits for tool-layer HTTP (docs/SECURITY_MODEL.md §6)."""

    timeout_s: float = Field(default=30.0, gt=0)
    max_response_bytes: int = Field(default=2_000_000, ge=1024)
    user_agent: str = "OIA-Bot/0.1 (+https://github.com/oia)"
    host_rate_limit_per_minute: int = Field(default=30, ge=1)


class ObservabilitySettings(BaseModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"
    service_name: str = "oia-backend"
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    mlflow_tracking_uri: str | None = None


class FineTuningSettings(BaseModel):
    """Active fine-tuned model selection and rollback (Phase 8)."""

    enabled: bool = False
    active_extraction_model: str | None = None
    rollback_extraction_model: str | None = None
    registry_name: str = "oia-extraction"
    noise_band: float = Field(default=0.02, ge=0.0, le=0.25)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    project_name: str = "Opportunity Intelligence Agent"
    version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    git_sha: str = "unknown"

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    egress: EgressSettings = Field(default_factory=EgressSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    finetuning: FineTuningSettings = Field(default_factory=FineTuningSettings)

    @property
    def docs_url(self) -> str | None:
        """OpenAPI docs are development-only; production exposes no schema UI."""
        return None if self.environment.is_production_like else "/docs"

    @model_validator(mode="after")
    def _harden_production(self) -> Settings:
        if not self.environment.is_production_like:
            return self

        problems: list[str] = []
        secret = self.security.secret_key.get_secret_value()
        if secret == DEV_SECRET_PLACEHOLDER or len(secret) < 32:
            problems.append("SECURITY__SECRET_KEY must be set to a value of at least 32 characters")
        if self.debug:
            problems.append("DEBUG must be false")
        if "*" in self.cors.origins:
            problems.append("CORS__ALLOW_ORIGINS must not contain a wildcard")
        if self.database.echo:
            problems.append("DATABASE__ECHO must be false (leaks data into logs)")
        if problems:
            raise ValueError(
                f"Invalid configuration for environment={self.environment}: " + "; ".join(problems)
            )
        return self

    @model_validator(mode="after")
    def _validate_driver(self) -> Settings:
        url = self.database.url
        if not (url.startswith("postgresql+asyncpg") or url.startswith("sqlite+aiosqlite")):
            raise ValueError(
                "DATABASE__URL must use an async driver: postgresql+asyncpg:// or sqlite+aiosqlite://"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Cached so that FastAPI dependencies and background workers observe the same
    object. Tests clear the cache via ``get_settings.cache_clear()``.
    """
    return Settings()


def generate_secret_key() -> str:
    """Helper used by ``scripts/`` to mint a deployment secret."""
    return secrets.token_urlsafe(48)
