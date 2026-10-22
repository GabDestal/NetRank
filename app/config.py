"""Application settings, read from environment variables and an optional `.env` file."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Each field is overridden by the environment variable of the same name."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")
    neo4j_database: str = "neo4j"
    log_level: str = "INFO"

    # Key for /api/admin/*; when unset the admin endpoints answer 503.
    admin_api_key: SecretStr | None = None
    # GDS Community caps concurrency at 4; tests and CI use 1 for reproducible KNN/Louvain.
    gds_concurrency: int = Field(default=4, ge=1, le=4)
    # Players need this many matches with serve statistics to get a style vector.
    style_min_matches: int = Field(default=50, ge=1)
    # Winner model written by make train (mounted read-only into the API container).
    model_path: str = "models/winner_model.json"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once on first use."""
    return Settings()
