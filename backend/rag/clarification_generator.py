"""Clarification question generation for ambiguous queries."""

from __future__ import annotations

import logging

from config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_CLARIFICATION_QUESTION = "我需要确认一下你指的是上一轮中的哪个报告、公司或指标？"

CLARIFICATION_SYSTEM_PROMPT = """你是一个多轮对话澄清助手。
请根据历史对话和当前问题，生成一句简短的澄清问题，帮助用户明确指代对象。
只输出追问句本身，不要输出解释、引号或 JSON。"""


class ClarificationGenerator:
    """Generate a short clarification question for ambiguous references."""

    def __init__(self, llm_client, settings: Settings | None = None) -> None:
        self.llm_client = llm_client
        self.settings = settings or get_settings()

    def generate(self, query: str, history_messages: list[dict[str, str]]) -> str:
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
                            "请输出一句澄清追问。"
                        ),
                    }
                ],
                system_prompt=CLARIFICATION_SYSTEM_PROMPT,
                model_name=getattr(self.settings, "fast_model_name", None),
            )
        except Exception as exc:  # pragma: no cover - runtime fallback
            logger.warning("Clarification generation failed: %s", exc)
            return DEFAULT_CLARIFICATION_QUESTION

        question = payload.strip() if isinstance(payload, str) else ""
        return question or DEFAULT_CLARIFICATION_QUESTION
