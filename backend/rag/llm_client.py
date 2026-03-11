"""OpenAI-compatible local LLM client."""

from __future__ import annotations

import logging

from urllib.parse import urlparse

from openai import AuthenticationError, BadRequestError, OpenAI

from config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "你是一个严谨的券商研报分析助手。"
    "你只能基于给定检索证据回答；"
    "证据不足时必须明确回答‘未找到足够依据’；"
    "禁止补充未在证据中出现的事实、数字、页码或结论。"
)


class LLMClient:
    """Call an OpenAI-compatible chat completion endpoint."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = OpenAI(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key or "MISSING_API_KEY",
        )

    def answer(self, prompt: str) -> str:
        """Generate an answer for the provided prompt."""
        return self.answer_messages([{"role": "user", "content": prompt}])

    def answer_messages(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> str:
        """Generate an answer for a multi-turn message list."""
        if not self.settings.api_key and not self._is_local_endpoint():
            raise RuntimeError(
                "LLM API key is missing. Set `LLM_API_KEY` "
                "(or `OPENAI_API_KEY` / `ZHIZENGZENG_API_KEY`) in your environment or `.env`."
            )
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model_name,
                messages=[{"role": "system", "content": system_prompt}, *messages],
                temperature=0.2,
            )
        except AuthenticationError as exc:  # pragma: no cover - depends on external LLM endpoint
            logger.exception("LLM authentication failed.")
            raise RuntimeError(
                "LLM authentication failed. Check `LLM_API_KEY` "
                "(or `OPENAI_API_KEY` / `ZHIZENGZENG_API_KEY`) and ensure it matches "
                f"the provider at {self.settings.base_url}."
            ) from exc
        except BadRequestError as exc:  # pragma: no cover - depends on external LLM endpoint
            logger.exception("LLM request was rejected.")
            raise RuntimeError(
                f"LLM request was rejected by {self.settings.base_url}: {exc}"
            ) from exc
        except Exception as exc:  # pragma: no cover - depends on external LLM endpoint
            logger.exception("LLM generation failed.")
            raise RuntimeError(
                f"LLM request failed. Ensure the OpenAI-compatible service is available at {self.settings.base_url}."
            ) from exc

        content = response.choices[0].message.content
        return content.strip() if content else "未生成有效回答。"

    def _is_local_endpoint(self) -> bool:
        """Return whether the configured endpoint points to a local server."""
        parsed = urlparse(self.settings.base_url)
        return parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}
