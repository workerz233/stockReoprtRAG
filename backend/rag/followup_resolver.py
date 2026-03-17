"""Resolve conversational followups into standalone retrieval queries."""

from __future__ import annotations

import json
import re
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
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            return self._build_passthrough_resolution(query=query, reason="快模型输出无法解析。")

        resolution = FollowupResolution(
            original_query=query,
            resolved_query=parsed.get("resolved_query") or query,
            is_followup=bool(parsed.get("is_followup")),
            confidence=float(parsed.get("confidence", 0.0)),
            needs_clarification=bool(parsed.get("needs_clarification")),
            clarification_question=parsed.get("clarification_question") or None,
            reason=str(parsed.get("reason") or ""),
        )
        return self._apply_thresholds(query=query, resolution=resolution)

    @staticmethod
    def _build_passthrough_resolution(query: str, reason: str) -> FollowupResolution:
        return FollowupResolution(
            original_query=query,
            resolved_query=query,
            is_followup=False,
            confidence=0.0,
            needs_clarification=False,
            clarification_question=None,
            reason=reason,
        )

    def _apply_thresholds(self, query: str, resolution: FollowupResolution) -> FollowupResolution:
        if not resolution.is_followup:
            return self._build_passthrough_resolution(query=query, reason=resolution.reason or "问题可独立理解。")

        if resolution.needs_clarification:
            return resolution

        threshold = float(getattr(self.settings, "followup_confidence_threshold", 0.8))
        if resolution.confidence >= threshold:
            return resolution

        if resolution.confidence >= 0.5 and self._has_strong_followup_signal(query):
            return resolution

        return FollowupResolution(
            original_query=query,
            resolved_query=None,
            is_followup=True,
            confidence=resolution.confidence,
            needs_clarification=True,
            clarification_question=(
                resolution.clarification_question
                or "我需要确认一下，你这句话是在延续上一轮哪个主题？"
            ),
            reason=resolution.reason or "追问置信度不足，需要澄清。",
        )

    @staticmethod
    def _has_strong_followup_signal(query: str) -> bool:
        patterns = (
            r"^那.+呢[？?]?$",
            r"^那\d{4}年呢[？?]?$",
            r"^它的.+呢[？?]?$",
            r"^(这个|那个).+呢[？?]?$",
            r"和另一篇比",
            r"上面提到的",
        )
        return any(re.search(pattern, query) for pattern in patterns)
