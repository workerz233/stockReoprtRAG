"""Local embedding client backed by Ollama."""

from __future__ import annotations

import logging
from typing import Sequence

import requests

from config import Settings, get_settings

logger = logging.getLogger(__name__)


class OllamaEmbeddingClient:
    """Generate embeddings through the local Ollama HTTP API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = requests.Session()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a list of texts sequentially."""
        embeddings = [self._request_embedding(text) for text in texts]
        logger.info("Generated %s embeddings.", len(embeddings))
        return embeddings

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        return self._request_embedding(query)

    def _request_embedding(self, text: str) -> list[float]:
        """Call Ollama's embedding endpoint."""
        payload = {
            "model": self.settings.embedding_model,
            "prompt": text,
        }

        try:
            response = self.session.post(
                self.settings.embedding_url,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Failed to request embedding from Ollama.")
            raise RuntimeError(
                f"Embedding request failed. Ensure Ollama is running at {self.settings.embedding_url}."
            ) from exc

        data = response.json()
        embedding = data.get("embedding")
        if not embedding:
            raise RuntimeError(f"Invalid embedding response: {data}")
        return [float(value) for value in embedding]
