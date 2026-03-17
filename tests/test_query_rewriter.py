import importlib
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


class QueryRewriterTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = lambda: None
        sys.modules["dotenv"] = fake_dotenv
        sys.modules.pop("backend.rag.query_rewriter", None)
        self.module = importlib.import_module("backend.rag.query_rewriter")
        self.settings = types.SimpleNamespace(fast_model_name="fast-model")

    def test_rewrite_uses_fast_model_name(self) -> None:
        llm_client = FakeLLMClient("华泰证券对存储行业2025年景气度的判断是什么？")
        rewriter = self.module.QueryRewriter(llm_client=llm_client, settings=self.settings)

        rewritten = rewriter.rewrite(
            "那2025年呢",
            history_messages=[
                {"role": "user", "content": "华泰证券怎么看存储行业景气度？"},
                {"role": "assistant", "content": "华泰证券认为行业景气度正在恢复。"},
            ],
        )

        self.assertEqual(rewritten, "华泰证券对存储行业2025年景气度的判断是什么？")
        self.assertEqual(llm_client.calls[0]["model_name"], "fast-model")

    def test_rewrite_falls_back_to_original_query_when_output_is_empty(self) -> None:
        llm_client = FakeLLMClient("")
        rewriter = self.module.QueryRewriter(llm_client=llm_client, settings=self.settings)

        rewritten = rewriter.rewrite(
            "那2025年呢",
            history_messages=[
                {"role": "user", "content": "华泰证券怎么看存储行业景气度？"},
                {"role": "assistant", "content": "华泰证券认为行业景气度正在恢复。"},
            ],
        )

        self.assertEqual(rewritten, "那2025年呢")


if __name__ == "__main__":
    unittest.main()
