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
        self.calls = []

    def answer_messages(self, messages, *, system_prompt=None, model_name=None):
        self.last_messages = messages
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "model_name": model_name,
            }
        )
        return "基于证据的回答"

    async def stream_answer_messages(self, messages, *, system_prompt=None, model_name=None):
        self.last_messages = messages
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "model_name": model_name,
                "stream": True,
            }
        )
        for chunk in ("基于", "证据", "的回答"):
            yield chunk


class FakeIntentRouter:
    def __init__(self, route_name: str, confidence: float = 0.91, reason: str = "semantic-router matched") -> None:
        self.route_name = route_name
        self.confidence = confidence
        self.reason = reason
        self.calls = []

    def route(self, query: str, history_messages: list[dict[str, str]]):
        self.calls.append((query, history_messages))
        return types.SimpleNamespace(
            route_name=self.route_name,
            confidence=self.confidence,
            reason=self.reason,
            query=query,
            history_messages=history_messages,
        )


class FakeRewriter:
    def __init__(self, rewritten_query: str) -> None:
        self.rewritten_query = rewritten_query
        self.calls = []

    def rewrite(self, query: str, history_messages: list[dict[str, str]]):
        self.calls.append((query, history_messages))
        return self.rewritten_query


class FakeClarificationGenerator:
    def __init__(self, question: str) -> None:
        self.question = question
        self.calls = []

    def generate(self, query: str, history_messages: list[dict[str, str]]):
        self.calls.append((query, history_messages))
        return self.question


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
            "backend.rag.intent_router": types.SimpleNamespace(IntentRouter=object),
            "backend.rag.query_rewriter": types.SimpleNamespace(QueryRewriter=object),
            "backend.rag.clarification_generator": types.SimpleNamespace(ClarificationGenerator=object),
            "backend.rag.llm_client": types.SimpleNamespace(LLMClient=object),
            "backend.rag.markdown_processor": types.SimpleNamespace(MarkdownProcessor=object),
            "backend.rag.milvus_store": types.SimpleNamespace(MilvusStore=object),
            "backend.rag.mineru_parser": types.SimpleNamespace(MinerUParser=object),
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

    def _build_pipeline(self):
        pipeline = self.module.ResearchRAGPipeline.__new__(self.module.ResearchRAGPipeline)
        pipeline.settings = types.SimpleNamespace(milvus_db_name="milvus.db", conversation_history_messages=6)
        pipeline.retriever = FakeRetriever()
        pipeline.llm_client = FakeLLMClient()
        pipeline.conversation_manager = FakeConversationManager()
        pipeline.intent_router = FakeIntentRouter("direct_retrieval")
        pipeline.query_rewriter = FakeRewriter("改写后的问题")
        pipeline.clarification_generator = FakeClarificationGenerator("你指的是哪篇报告？")
        return pipeline

    def test_answer_question_chitchat_skips_retrieval_and_persists_messages(self) -> None:
        pipeline = self._build_pipeline()
        pipeline.intent_router = FakeIntentRouter("chitchat")

        result = pipeline.answer_question("demo", "你好", conversation_id="conv-1")

        self.assertEqual(result["type"], "answer")
        self.assertEqual(result["resolved_query"], None)
        self.assertEqual(result["answer"], "基于证据的回答")
        self.assertIsNone(pipeline.retriever.last_query)
        self.assertEqual(pipeline.conversation_manager.appended[0][2]["content"], "你好")

    def test_answer_question_history_qa_uses_history_without_retrieval(self) -> None:
        pipeline = self._build_pipeline()
        pipeline.intent_router = FakeIntentRouter("history_qa")

        result = pipeline.answer_question("demo", "总结一下上文", conversation_id="conv-1")

        self.assertEqual(result["type"], "answer")
        self.assertIsNone(result["resolved_query"])
        self.assertIsNone(pipeline.retriever.last_query)
        self.assertEqual([message["role"] for message in pipeline.llm_client.last_messages[:2]], ["user", "assistant"])

    def test_answer_question_history_rewrite_route_uses_rewritten_query_for_retrieval(self) -> None:
        pipeline = self._build_pipeline()
        pipeline.intent_router = FakeIntentRouter("history_rewrite_retrieval")
        pipeline.query_rewriter = FakeRewriter("华泰证券对存储行业2025年景气度的判断是什么？")

        result = pipeline.answer_question("demo", "那2025年呢", conversation_id="conv-1")

        self.assertEqual(result["resolved_query"], "华泰证券对存储行业2025年景气度的判断是什么？")
        self.assertEqual(
            pipeline.retriever.last_query,
            "华泰证券对存储行业2025年景气度的判断是什么？",
        )

    def test_answer_question_direct_retrieval_uses_original_query(self) -> None:
        pipeline = self._build_pipeline()
        pipeline.intent_router = FakeIntentRouter("direct_retrieval")

        result = pipeline.answer_question("demo", "宁德时代2025年盈利预测是多少", conversation_id="conv-1")

        self.assertEqual(result["resolved_query"], "宁德时代2025年盈利预测是多少")
        self.assertEqual(pipeline.retriever.last_query, "宁德时代2025年盈利预测是多少")

    def test_answer_question_returns_clarification_without_retrieval(self) -> None:
        pipeline = self._build_pipeline()
        pipeline.intent_router = FakeIntentRouter("clarification", reason="信息不足")
        pipeline.clarification_generator = FakeClarificationGenerator("你指的是华泰证券还是华西证券这篇报告？")

        result = pipeline.answer_question("demo", "它的毛利率呢", conversation_id="conv-1")

        self.assertEqual(result["type"], "clarification")
        self.assertEqual(result["answer"], "你指的是华泰证券还是华西证券这篇报告？")
        self.assertEqual(result["sources"], [])
        self.assertIsNone(result["resolved_query"])
        self.assertIsNone(pipeline.retriever.last_query)

    def test_stream_answer_question_emits_final_sources_and_persists_messages(self) -> None:
        pipeline = self._build_pipeline()
        pipeline.intent_router = FakeIntentRouter("direct_retrieval")

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

    def test_stream_answer_question_skips_retrieval_for_chitchat(self) -> None:
        pipeline = self._build_pipeline()
        pipeline.intent_router = FakeIntentRouter("chitchat")

        async def collect_events():
            return [
                event
                async for event in pipeline.stream_answer_question(
                    "demo",
                    "你好",
                    conversation_id="conv-1",
                )
            ]

        events = asyncio.run(collect_events())

        self.assertEqual(events[-1]["resolved_query"], None)
        self.assertEqual(events[-1]["answer"], "基于证据的回答")
        self.assertIsNone(pipeline.retriever.last_query)

    def test_stream_answer_question_returns_clarification_done_event(self) -> None:
        pipeline = self._build_pipeline()
        pipeline.intent_router = FakeIntentRouter("clarification", reason="存在多个候选主体。")
        pipeline.clarification_generator = FakeClarificationGenerator("你指的是哪篇报告？")

        async def collect_events():
            return [
                event
                async for event in pipeline.stream_answer_question(
                    "demo",
                    "它怎么样",
                    conversation_id="conv-1",
                )
            ]

        events = asyncio.run(collect_events())

        self.assertEqual([event["type"] for event in events], ["start", "delta", "done"])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["clarification"]["question"], "你指的是哪篇报告？")
        self.assertIsNone(pipeline.retriever.last_query)


if __name__ == "__main__":
    unittest.main()
