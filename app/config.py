"""Runtime settings loaded from environment variables (and an optional .env file)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Application settings."""

    log_level: str
    data_dir: Path
    nvd_api_key: str = field(default="", repr=False)

    @property
    def raw_dir(self) -> Path:
        """Directory holding downloaded source datasets."""
        return self.data_dir / "raw"


def load_settings(env_file: str | None = ".env") -> Settings:
    """Build Settings from the environment, reading env_file first if it exists."""
    if env_file:
        load_dotenv(env_file, override=False)
    return Settings(
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        data_dir=Path(os.getenv("DATA_DIR", "data")),
        nvd_api_key=os.getenv("NVD_API_KEY", ""),
    )
