import importlib
import asyncio
import sys
import types
import unittest


class FakeCompletions:
    def __init__(self) -> None:
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if kwargs.get("stream"):
            return iter(
                [
                    types.SimpleNamespace(
                        choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content="第一段"))]
                    ),
                    types.SimpleNamespace(
                        choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content=None))]
                    ),
                    types.SimpleNamespace(
                        choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content="第二段"))]
                    ),
                ]
            )
        message = types.SimpleNamespace(content="  好的回答  ")
        choice = types.SimpleNamespace(message=message)
        return types.SimpleNamespace(choices=[choice])


class FakeAsyncCompletions:
    def __init__(self) -> None:
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeAsyncStream()


class FakeAsyncStream:
    def __aiter__(self):
        async def generator():
            yield types.SimpleNamespace(
                choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content="第一段"))]
            )
            yield types.SimpleNamespace(
                choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content=None))]
            )
            yield types.SimpleNamespace(
                choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content="第二段"))]
            )

        return generator()


class FakeOpenAIClient:
    def __init__(self, **kwargs) -> None:
        self.chat = types.SimpleNamespace(completions=FakeCompletions())


class FakeAsyncOpenAIClient:
    def __init__(self, **kwargs) -> None:
        self.chat = types.SimpleNamespace(completions=FakeAsyncCompletions())


class LLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_openai = types.ModuleType("openai")
        fake_openai.AuthenticationError = type("AuthenticationError", (Exception,), {})
        fake_openai.BadRequestError = type("BadRequestError", (Exception,), {})
        fake_openai.OpenAI = FakeOpenAIClient
        fake_openai.AsyncOpenAI = FakeAsyncOpenAIClient
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

    def test_answer_messages_allows_model_override(self) -> None:
        settings = self.module.Settings(
            base_url="http://localhost:8001/v1",
            model_name="main-model",
            fast_model_name="fast-model",
            api_key="token",
        )
        client = self.module.LLMClient(settings=settings)

        answer = client.answer_messages(
            [{"role": "user", "content": "测试问题"}],
            model_name="fast-model",
        )

        self.assertEqual(answer, "好的回答")
        self.assertEqual(client.client.chat.completions.last_kwargs["model"], "fast-model")

    def test_stream_answer_messages_yields_content_chunks(self) -> None:
        client = self.module.LLMClient(settings=self.settings)

        async def collect_chunks():
            return [chunk async for chunk in client.stream_answer_messages([{"role": "user", "content": "流式问题"}])]

        chunks = asyncio.run(collect_chunks())

        self.assertEqual(chunks, ["第一段", "第二段"])
        self.assertTrue(client.async_client.chat.completions.last_kwargs["stream"])


if __name__ == "__main__":
    unittest.main()
