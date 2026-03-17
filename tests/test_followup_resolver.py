import importlib
import json
import sys
import types
import unittest


class FakeLLMClient:
    def __init__(self, response_text: str = "") -> None:
        self.response_text = response_text
        self.calls = []

    def answer_messages(self, messages, *, system_prompt=None, model_name=None):
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "model_name": model_name,
            }
        )
        return self.response_text


class FollowupResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = lambda: None
        sys.modules["dotenv"] = fake_dotenv
        sys.modules.pop("backend.rag.followup_resolver", None)
        self.module = importlib.import_module("backend.rag.followup_resolver")
        self.settings = types.SimpleNamespace(
            fast_model_name="fast-model",
            followup_confidence_threshold=0.8,
        )

    def test_independent_query_passes_through(self) -> None:
        resolver = self.module.FollowupResolver(llm_client=FakeLLMClient(), settings=self.settings)

        result = resolver.resolve("存储行业景气度怎么看", history_messages=[])

        self.assertFalse(result.is_followup)
        self.assertEqual(result.resolved_query, "存储行业景气度怎么看")
        self.assertFalse(result.needs_clarification)

    def test_followup_query_is_rewritten(self) -> None:
        llm_client = FakeLLMClient(
            json.dumps(
                {
                    "is_followup": True,
                    "resolved_query": "华泰证券对存储行业2025年景气度的判断是什么？",
                    "confidence": 0.91,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "reason": "当前问题依赖上一轮主题。",
                },
                ensure_ascii=False,
            )
        )
        resolver = self.module.FollowupResolver(llm_client=llm_client, settings=self.settings)

        result = resolver.resolve(
            "那2025年呢",
            history_messages=[
                {"role": "user", "content": "华泰证券怎么判断存储行业景气度？"},
                {"role": "assistant", "content": "华泰证券认为行业景气度正在恢复。"},
            ],
        )

        self.assertTrue(result.is_followup)
        self.assertEqual(result.resolved_query, "华泰证券对存储行业2025年景气度的判断是什么？")
        self.assertFalse(result.needs_clarification)
        self.assertEqual(llm_client.calls[0]["model_name"], "fast-model")

    def test_ambiguous_reference_requests_clarification(self) -> None:
        llm_client = FakeLLMClient(
            json.dumps(
                {
                    "is_followup": True,
                    "resolved_query": "",
                    "confidence": 0.62,
                    "needs_clarification": True,
                    "clarification_question": "你指的是华泰证券还是华西证券这篇报告？",
                    "reason": "历史中存在两个候选主体。",
                },
                ensure_ascii=False,
            )
        )
        resolver = self.module.FollowupResolver(llm_client=llm_client, settings=self.settings)

        result = resolver.resolve(
            "它的毛利率呢",
            history_messages=[
                {"role": "user", "content": "华泰证券怎么看存储？"},
                {"role": "assistant", "content": "华泰证券认为基本面改善。"},
                {"role": "user", "content": "华西证券怎么看存储？"},
                {"role": "assistant", "content": "华西证券更强调价格修复。"},
            ],
        )

        self.assertTrue(result.is_followup)
        self.assertTrue(result.needs_clarification)
        self.assertEqual(result.clarification_question, "你指的是华泰证券还是华西证券这篇报告？")


if __name__ == "__main__":
    unittest.main()
