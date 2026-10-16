"""Runtime settings loaded from environment variables (and an optional .env file)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Default model per LLM provider (D19). LLM_MODEL in .env overrides it. On Groq, qwen3.8-27b is the default:
# openai/gpt-oss-120b is larger but often returned empty replies or malformed tool calls in our tests.
DEFAULT_MODELS = {"groq": "qwen/qwen3.8-27b", "anthropic": "claude-haiku-5-5", "ollama": "qwen2.5:3b"}


@dataclass(frozen=True)
class Settings:  # pylint: disable=too-many-instance-attributes
    """Application settings. Secrets are excluded from repr so they never reach logs."""

    log_level: str
    data_dir: Path
    nvd_api_key: str = field(default="", repr=False)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = field(default="", repr=False)
    llm_provider: str = "groq"
    llm_model: str = DEFAULT_MODELS["groq"]
    groq_api_key: str = field(default="", repr=False)
    anthropic_api_key: str = field(default="", repr=False)
    ollama_base_url: str = "http://localhost:11434"
    llm_max_retries: int = 6

    @property
    def raw_dir(self) -> Path:
        """Directory holding downloaded source datasets."""
        return self.data_dir / "raw"


def load_settings(env_file: str | None = ".env") -> Settings:
    """Build Settings from the environment, reading env_file first if it exists."""
    if env_file:
        load_dotenv(env_file, override=False)
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    return Settings(
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        data_dir=Path(os.getenv("DATA_DIR", "data")),
        nvd_api_key=os.getenv("NVD_API_KEY", ""),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
        llm_provider=provider,
        llm_model=os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider, ""),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "6")),
    )
