"""Semantic intent router for chat queries."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from config import BASE_DIR, Settings, get_settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by import stubs in tests
    from semantic_router import Route
    from semantic_router.encoders import OllamaEncoder
    from semantic_router.routers import SemanticRouter
except ImportError:  # pragma: no cover - fallback path covered instead
    Route = None
    OllamaEncoder = None
    SemanticRouter = None


@dataclass(frozen=True)
class RouteDecision:
    """Normalized route result consumed by the pipeline."""

    route_name: str
    confidence: float
    reason: str
    query: str
    history_messages: list[dict[str, str]]


class IntentRouter:
    """Route each query into one semantic intent bucket."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        route_config_path: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.route_config_path = route_config_path or (BASE_DIR / "config" / "semantic_routes.json")
        self.router = self._build_router()

    def _build_router(self):
        if Route is None or OllamaEncoder is None or SemanticRouter is None:
            logger.warning("semantic-router is unavailable; using fallback intent routing.")
            return None

        try:
            routes = self._load_route_definitions()
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Failed to load semantic route config: %s", exc)
            return None

        embedding_base_url = self._derive_embedding_base_url(self.settings.embedding_url)
        encoder = OllamaEncoder(
            name=self.settings.embedding_model,
            base_url=embedding_base_url,
        )
        return SemanticRouter(encoder=encoder, routes=routes, auto_sync="local")

    def _load_route_definitions(self) -> list[object]:
        payload = json.loads(self.route_config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Route config must be a list.")

        routes = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Each route config entry must be an object.")
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            utterances = item.get("utterances") or []
            if not name or not isinstance(utterances, list) or not utterances:
                raise ValueError("Each route must define a name and non-empty utterances.")
            routes.append(Route(name=name, utterances=[str(text) for text in utterances], description=description))
        return routes

    def route(self, query: str, history_messages: list[dict[str, str]]) -> RouteDecision:
        normalized_query = query.strip()
        if not self.router:
            return self._fallback_route(normalized_query, history_messages, reason="fallback: semantic-router unavailable")

        try:
            result = self.router(normalized_query)
        except Exception as exc:  # pragma: no cover - depends on runtime backend
            logger.warning("semantic-router failed: %s", exc)
            return self._fallback_route(normalized_query, history_messages, reason="fallback: semantic-router execution failed")

        route_name = getattr(result, "name", "") or "direct_retrieval"
        confidence = float(getattr(result, "similarity_score", 0.0) or 0.0)
        return RouteDecision(
            route_name=route_name,
            confidence=confidence,
            reason=f"semantic-router matched {route_name}",
            query=normalized_query,
            history_messages=list(history_messages),
        )

    def _fallback_route(
        self,
        query: str,
        history_messages: list[dict[str, str]],
        *,
        reason: str,
    ) -> RouteDecision:
        if history_messages and self._looks_like_history_qa(query):
            route_name = "history_qa"
        elif history_messages and self._looks_like_short_pronoun(query):
            route_name = "clarification"
        else:
            route_name = "direct_retrieval"
        return RouteDecision(
            route_name=route_name,
            confidence=0.0,
            reason=reason,
            query=query,
            history_messages=list(history_messages),
        )

    @staticmethod
    def _derive_embedding_base_url(embedding_url: str) -> str:
        parsed = urlparse(embedding_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return embedding_url.rstrip("/")

    @staticmethod
    def _looks_like_history_qa(query: str) -> bool:
        markers = ("总结", "归纳", "概括", "回顾", "上文", "前面", "刚才")
        return any(marker in query for marker in markers)

    @staticmethod
    def _looks_like_short_pronoun(query: str) -> bool:
        pronouns = ("它", "那个", "这个", "这篇", "那篇", "这个结论")
        return len(query) <= 12 and any(token in query for token in pronouns)
