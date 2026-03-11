import importlib
import sys
import types
import unittest


class FakeCompletions:
    def __init__(self) -> None:
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        message = types.SimpleNamespace(content="  好的回答  ")
        choice = types.SimpleNamespace(message=message)
        return types.SimpleNamespace(choices=[choice])


class FakeOpenAIClient:
    def __init__(self, **kwargs) -> None:
        self.chat = types.SimpleNamespace(completions=FakeCompletions())


class LLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_openai = types.ModuleType("openai")
        fake_openai.AuthenticationError = type("AuthenticationError", (Exception,), {})
        fake_openai.BadRequestError = type("BadRequestError", (Exception,), {})
        fake_openai.OpenAI = FakeOpenAIClient
        sys.modules["openai"] = fake_openai

        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = lambda: None
        sys.modules["dotenv"] = fake_dotenv

        sys.modules.pop("backend.rag.llm_client", None)
        sys.modules.pop("config", None)
        self.module = importlib.import_module("backend.rag.llm_client")
        self.settings = self.module.Settings(base_url="http://localhost:8001/v1", model_name="demo", api_key="token")

    def test_answer_messages_forwards_history_and_trims_content(self) -> None:
        client = self.module.LLMClient(settings=self.settings)

        answer = client.answer_messages(
            [
                {"role": "user", "content": "第一问"},
                {"role": "assistant", "content": "第一答"},
                {"role": "user", "content": "第二问"},
            ]
        )

        self.assertEqual(answer, "好的回答")
        sent_messages = client.client.chat.completions.last_kwargs["messages"]
        self.assertEqual(sent_messages[1:], [
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一答"},
            {"role": "user", "content": "第二问"},
        ])


if __name__ == "__main__":
    unittest.main()
