import asyncio
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path


class FakeRetriever:
    def __init__(self) -> None:
        self.last_query = None

    def retrieve(self, project_name: str, query: str):
        self.last_query = query
        return [
            types.SimpleNamespace(
                report_name="demo.pdf",
                section_path="核心观点",
                page_no=3,
                score=0.91,
                text="收入增速回升。",
                block_type="paragraph",
            )
        ]


class FakeLLMClient:
    def __init__(self) -> None:
        self.last_messages = None

    def answer_messages(self, messages):
        self.last_messages = messages
        return "基于证据的回答"

    async def stream_answer_messages(self, messages):
        self.last_messages = messages
        for chunk in ("基于", "证据", "的回答"):
            yield chunk


class FakeResolver:
    def __init__(self, resolution) -> None:
        self.resolution = resolution
        self.calls = []

    @classmethod
    def resolved(cls, query: str):
        return cls(
            types.SimpleNamespace(
                original_query="",
                resolved_query=query,
                is_followup=True,
                confidence=0.91,
                needs_clarification=False,
                clarification_question=None,
                reason="依赖上一轮主题。",
            )
        )

    @classmethod
    def clarification(cls, question: str):
        return cls(
            types.SimpleNamespace(
                original_query="",
                resolved_query=None,
                is_followup=True,
                confidence=0.62,
                needs_clarification=True,
                clarification_question=question,
                reason="存在多个候选主体。",
            )
        )

    def resolve(self, query: str, history_messages: list[dict[str, str]]):
        self.calls.append((query, history_messages))
        return self.resolution


class FakeConversationManager:
    def __init__(self) -> None:
        self.created = []
        self.appended = []
        self.messages = {
            "conv-1": [
                {"role": "user", "content": "上一问"},
                {"role": "assistant", "content": "上一答"},
            ]
        }

    def create_conversation(self, project_name: str):
        self.created.append(project_name)
        self.messages["conv-new"] = []
        return {"conversation_id": "conv-new", "title": "新对话"}

    def get_conversation(self, project_name: str, conversation_id: str):
        return {"conversation_id": conversation_id, "messages": list(self.messages[conversation_id])}

    def append_message(self, project_name: str, conversation_id: str, **kwargs):
        self.appended.append((project_name, conversation_id, kwargs))
        self.messages.setdefault(conversation_id, []).append(kwargs)


class PipelineConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        stub_modules = {
            "dotenv": types.SimpleNamespace(load_dotenv=lambda: None),
            "backend.rag.chunker": types.SimpleNamespace(DocumentChunker=object),
            "backend.rag.embeddings": types.SimpleNamespace(OllamaEmbeddingClient=object),
            "backend.rag.llm_client": types.SimpleNamespace(LLMClient=object),
            "backend.rag.markdown_processor": types.SimpleNamespace(MarkdownProcessor=object),
            "backend.rag.milvus_store": types.SimpleNamespace(MilvusStore=object),
            "backend.rag.mineru_parser": types.SimpleNamespace(MinerUParser=object),
            "backend.rag.followup_resolver": types.SimpleNamespace(FollowupResolver=object),
            "backend.rag.retriever": types.SimpleNamespace(MilvusRetriever=object),
            "config": types.SimpleNamespace(
                PROJECTS_DIR=Path(tempfile.gettempdir()) / "stock-rag-tests",
                ensure_base_directories=lambda: None,
                get_settings=lambda: types.SimpleNamespace(milvus_db_name="milvus.db", conversation_history_messages=6),
            ),
        }
        for name, module in stub_modules.items():
            sys.modules[name] = module

        sys.modules.pop("backend.rag.pipeline", None)
        self.module = importlib.import_module("backend.rag.pipeline")

    def test_answer_question_includes_history_and_persists_messages(self) -> None:
        pipeline = self.module.ResearchRAGPipeline.__new__(self.module.ResearchRAGPipeline)
        pipeline.settings = types.SimpleNamespace(milvus_db_name="milvus.db", conversation_history_messages=6)
        pipeline.retriever = FakeRetriever()
        pipeline.llm_client = FakeLLMClient()
        pipeline.conversation_manager = FakeConversationManager()
        pipeline.followup_resolver = FakeResolver.resolved("这一轮问题")

        result = pipeline.answer_question("demo", "这一轮问题", conversation_id="conv-1")

        self.assertEqual(result["conversation_id"], "conv-1")
        self.assertEqual(result["answer"], "基于证据的回答")
        self.assertEqual([message["role"] for message in pipeline.llm_client.last_messages[:2]], ["user", "assistant"])
        self.assertIn("这一轮问题", pipeline.llm_client.last_messages[-1]["content"])
        self.assertEqual(pipeline.conversation_manager.appended[0][2]["content"], "这一轮问题")
        self.assertEqual(pipeline.conversation_manager.appended[1][2]["content"], "基于证据的回答")

    def test_stream_answer_question_emits_final_sources_and_persists_messages(self) -> None:
        pipeline = self.module.ResearchRAGPipeline.__new__(self.module.ResearchRAGPipeline)
        pipeline.settings = types.SimpleNamespace(milvus_db_name="milvus.db", conversation_history_messages=6)
        pipeline.retriever = FakeRetriever()
        pipeline.llm_client = FakeLLMClient()
        pipeline.conversation_manager = FakeConversationManager()
        pipeline.followup_resolver = FakeResolver.resolved("这一轮问题")

        async def collect_events():
            return [
                event
                async for event in pipeline.stream_answer_question(
                    "demo",
                    "这一轮问题",
                    conversation_id="conv-1",
                )
            ]

        events = asyncio.run(collect_events())

        self.assertEqual(events[0]["type"], "start")
        self.assertEqual([event["delta"] for event in events[1:-1]], ["基于", "证据", "的回答"])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["answer"], "基于证据的回答")
        self.assertEqual(events[-1]["sources"][0]["report_name"], "demo.pdf")
        self.assertEqual(pipeline.conversation_manager.appended[0][2]["content"], "这一轮问题")
        self.assertEqual(pipeline.conversation_manager.appended[1][2]["content"], "基于证据的回答")

    def test_answer_question_uses_resolved_query_for_retrieval(self) -> None:
        pipeline = self.module.ResearchRAGPipeline.__new__(self.module.ResearchRAGPipeline)
        pipeline.settings = types.SimpleNamespace(milvus_db_name="milvus.db", conversation_history_messages=6)
        pipeline.retriever = FakeRetriever()
        pipeline.llm_client = FakeLLMClient()
        pipeline.conversation_manager = FakeConversationManager()
        pipeline.followup_resolver = FakeResolver.resolved("华泰证券对存储行业2025年景气度的判断是什么？")

        result = pipeline.answer_question("demo", "那2025年呢", conversation_id="conv-1")

        self.assertEqual(
            pipeline.retriever.last_query,
            "华泰证券对存储行业2025年景气度的判断是什么？",
        )
        self.assertEqual(result["answer"], "基于证据的回答")

    def test_answer_question_returns_clarification_without_retrieval(self) -> None:
        pipeline = self.module.ResearchRAGPipeline.__new__(self.module.ResearchRAGPipeline)
        pipeline.settings = types.SimpleNamespace(milvus_db_name="milvus.db", conversation_history_messages=6)
        pipeline.retriever = FakeRetriever()
        pipeline.llm_client = FakeLLMClient()
        pipeline.conversation_manager = FakeConversationManager()
        pipeline.followup_resolver = FakeResolver.clarification("你指的是华泰证券还是华西证券这篇报告？")

        result = pipeline.answer_question("demo", "它的毛利率呢", conversation_id="conv-1")

        self.assertEqual(result["type"], "clarification")
        self.assertEqual(result["answer"], "你指的是华泰证券还是华西证券这篇报告？")
        self.assertEqual(result["sources"], [])
        self.assertIsNone(pipeline.retriever.last_query)


if __name__ == "__main__":
    unittest.main()
