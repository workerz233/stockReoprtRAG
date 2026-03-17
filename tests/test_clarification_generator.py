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


class ClarificationGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = lambda: None
        sys.modules["dotenv"] = fake_dotenv
        sys.modules.pop("backend.rag.clarification_generator", None)
        self.module = importlib.import_module("backend.rag.clarification_generator")
        self.settings = types.SimpleNamespace(fast_model_name="fast-model")

    def test_generate_uses_fast_model_name(self) -> None:
        llm_client = FakeLLMClient("你指的是上一轮中的哪家公司或哪篇报告？")
        generator = self.module.ClarificationGenerator(llm_client=llm_client, settings=self.settings)

        question = generator.generate(
            "它怎么样",
            history_messages=[
                {"role": "user", "content": "华泰证券怎么看存储？"},
                {"role": "assistant", "content": "华泰证券认为基本面改善。"},
            ],
        )

        self.assertEqual(question, "你指的是上一轮中的哪家公司或哪篇报告？")
        self.assertEqual(llm_client.calls[0]["model_name"], "fast-model")

    def test_generate_falls_back_to_default_question_when_output_is_empty(self) -> None:
        llm_client = FakeLLMClient("")
        generator = self.module.ClarificationGenerator(llm_client=llm_client, settings=self.settings)

        question = generator.generate(
            "它怎么样",
            history_messages=[
                {"role": "user", "content": "华泰证券怎么看存储？"},
                {"role": "assistant", "content": "华泰证券认为基本面改善。"},
            ],
        )

        self.assertEqual(question, self.module.DEFAULT_CLARIFICATION_QUESTION)


if __name__ == "__main__":
    unittest.main()
