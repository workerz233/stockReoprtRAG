"""Application configuration and shared paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
FRONTEND_DIR = BASE_DIR / "frontend"


def _normalize_base_url(raw_url: str) -> str:
    """Normalize OpenAI-compatible base URLs to the expected root form."""
    normalized = raw_url.strip().strip('"').strip("'").rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.rstrip("/")


def _normalize_optional_env(raw_value: str | None) -> str | None:
    """Normalize optional string environment variables."""
    if raw_value is None:
        return None
    normalized = raw_value.strip().strip('"').strip("'")
    return normalized or None


def _is_local_base_url(base_url: str) -> bool:
    """Return whether the configured LLM endpoint points to a local service."""
    parsed = urlparse(base_url)
    return parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}


@dataclass(frozen=True)
class Settings:
    """Container for runtime settings."""

    base_url: str
    model_name: str
    api_key: str | None = None
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_url: str = "http://localhost:11434/api/embeddings"
    chunk_size: int = 600
    chunk_overlap: int = 100
    top_k: int = 10
    milvus_db_name: str = "milvus.db"
    conversation_history_messages: int = 8


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings from environment variables."""
    raw_base_url = os.getenv("BASE_URL", "http://localhost:8001/v1")
    base_url = _normalize_base_url(raw_base_url)
    model_name = os.getenv("MODEL_NAME", "qwen2.5-7b-instruct").strip().strip('"').strip("'")
    api_key = (
        _normalize_optional_env(os.getenv("LLM_API_KEY"))
        or _normalize_optional_env(os.getenv("OPENAI_API_KEY"))
        or _normalize_optional_env(os.getenv("ZHIZENGZENG_API_KEY"))
    )
    return Settings(
        base_url=base_url,
        model_name=model_name,
        api_key=api_key if api_key else ("EMPTY" if _is_local_base_url(base_url) else None),
        conversation_history_messages=max(0, int(os.getenv("CONVERSATION_HISTORY_MESSAGES", "8"))),
    )


def ensure_base_directories() -> None:
    """Create required top-level directories."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
