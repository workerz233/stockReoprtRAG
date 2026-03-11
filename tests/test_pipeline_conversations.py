import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path


class FakeRetriever:
    def retrieve(self, project_name: str, query: str):
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

        result = pipeline.answer_question("demo", "这一轮问题", conversation_id="conv-1")

        self.assertEqual(result["conversation_id"], "conv-1")
        self.assertEqual(result["answer"], "基于证据的回答")
        self.assertEqual([message["role"] for message in pipeline.llm_client.last_messages[:2]], ["user", "assistant"])
        self.assertIn("这一轮问题", pipeline.llm_client.last_messages[-1]["content"])
        self.assertEqual(pipeline.conversation_manager.appended[0][2]["content"], "这一轮问题")
        self.assertEqual(pipeline.conversation_manager.appended[1][2]["content"], "基于证据的回答")


if __name__ == "__main__":
    unittest.main()
