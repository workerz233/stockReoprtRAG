"""Resolve conversational followups into standalone retrieval queries."""

from __future__ import annotations

import json
from dataclasses import dataclass

from config import Settings, get_settings

FOLLOWUP_SYSTEM_PROMPT = """你是一个查询改写器。
你必须根据当前问题和历史对话，输出一个 JSON 对象，包含以下字段：
- is_followup: bool
- resolved_query: string
- confidence: number
- needs_clarification: bool
- clarification_question: string
- reason: string

如果当前问题不依赖历史上下文，也必须输出完整 JSON。"""


@dataclass(frozen=True)
class FollowupResolution:
    """Structured result for one user query."""

    original_query: str
    resolved_query: str | None
    is_followup: bool
    confidence: float
    needs_clarification: bool
    clarification_question: str | None
    reason: str


class FollowupResolver:
    """Use a fast LLM to rewrite conversational followups before retrieval."""

    def __init__(self, llm_client, settings: Settings | None = None) -> None:
        self.llm_client = llm_client
        self.settings = settings or get_settings()

    def resolve(
        self,
        query: str,
        history_messages: list[dict[str, str]],
    ) -> FollowupResolution:
        query = query.strip()
        if not history_messages:
            return FollowupResolution(
                original_query=query,
                resolved_query=query,
                is_followup=False,
                confidence=1.0,
                needs_clarification=False,
                clarification_question=None,
                reason="没有可用历史消息。",
            )

        history_text = "\n".join(
            f"{message['role']}: {message['content']}"
            for message in history_messages
            if message.get("role") and message.get("content")
        )
        payload = self.llm_client.answer_messages(
            [
                {
                    "role": "user",
                    "content": (
                        f"历史对话:\n{history_text}\n\n"
                        f"当前问题:\n{query}\n\n"
                        "请输出 JSON。"
                    ),
                }
            ],
            system_prompt=FOLLOWUP_SYSTEM_PROMPT,
            model_name=getattr(self.settings, "fast_model_name", None),
        )
        parsed = json.loads(payload)
        return FollowupResolution(
            original_query=query,
            resolved_query=parsed.get("resolved_query") or query,
            is_followup=bool(parsed.get("is_followup")),
            confidence=float(parsed.get("confidence", 0.0)),
            needs_clarification=bool(parsed.get("needs_clarification")),
            clarification_question=parsed.get("clarification_question") or None,
            reason=str(parsed.get("reason") or ""),
        )
