"""Query rewriting for history-dependent retrieval questions."""

from __future__ import annotations

import logging

from config import Settings, get_settings

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = """你是一个研报检索查询改写器。
请根据历史对话和当前问题，把当前问题改写成一个可独立检索的完整问题。
只输出改写后的问题，不要输出解释、引号或 JSON。"""


class QueryRewriter:
    """Rewrite context-dependent queries into standalone retrieval queries."""

    def __init__(self, llm_client, settings: Settings | None = None) -> None:
        self.llm_client = llm_client
        self.settings = settings or get_settings()

    def rewrite(self, query: str, history_messages: list[dict[str, str]]) -> str:
        normalized_query = query.strip()
        history_text = "\n".join(
            f"{message['role']}: {message['content']}"
            for message in history_messages
            if message.get("role") and message.get("content")
        )
        try:
            payload = self.llm_client.answer_messages(
                [
                    {
                        "role": "user",
                        "content": (
                            f"历史对话:\n{history_text or '无'}\n\n"
                            f"当前问题:\n{normalized_query}\n\n"
                            "请输出改写后的独立检索问题。"
                        ),
                    }
                ],
                system_prompt=REWRITE_SYSTEM_PROMPT,
                model_name=getattr(self.settings, "fast_model_name", None),
            )
        except Exception as exc:  # pragma: no cover - runtime fallback
            logger.warning("Query rewriting failed: %s", exc)
            return normalized_query

        rewritten_query = payload.strip() if isinstance(payload, str) else ""
        return rewritten_query or normalized_query
