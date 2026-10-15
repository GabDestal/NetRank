"""Runtime settings loaded from environment variables (and an optional .env file)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Application settings."""

    log_level: str
    data_dir: Path


def load_settings(env_file: str | None = ".env") -> Settings:
    """Build Settings from the environment, reading env_file first if it exists."""
    if env_file:
        load_dotenv(env_file, override=False)
    return Settings(
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        data_dir=Path(os.getenv("DATA_DIR", "data")),
    )
