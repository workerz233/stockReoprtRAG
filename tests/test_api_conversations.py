import importlib
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.conversation_manager import ConversationManager
from backend.project_manager import ProjectManager


class FakePipeline:
    def __init__(self) -> None:
        self.last_call = None

    def stream_answer_question(self, project_name: str, query: str, conversation_id: str | None = None):
        self.last_call = (project_name, query, conversation_id)
        yield {"type": "start", "conversation_id": conversation_id or "conv-new"}
        yield {"type": "delta", "delta": "第一段"}
        yield {"type": "done", "conversation_id": conversation_id or "conv-new", "answer": "第一段"}


class ConversationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.project_manager = ProjectManager(projects_dir=Path(self.temp_dir.name))
        self.project_manager.create_project("demo")
        self.conversation_manager = ConversationManager(self.project_manager)

        self.app_module = importlib.import_module("app")
        self.app_module.project_manager = self.project_manager
        self.app_module.conversation_manager = self.conversation_manager
        self.app_module.pipeline = FakePipeline()
        self.client = TestClient(self.app_module.app)

    def test_create_list_get_and_delete_conversation(self) -> None:
        create_response = self.client.post("/api/projects/demo/conversations")
        self.assertEqual(create_response.status_code, 200)
        conversation_id = create_response.json()["conversation_id"]

        list_response = self.client.get("/api/projects/demo/conversations")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["conversations"]), 1)

        get_response = self.client.get(f"/api/projects/demo/conversations/{conversation_id}")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["conversation_id"], conversation_id)
        self.assertEqual(get_response.json()["messages"], [])

        delete_response = self.client.delete(f"/api/projects/demo/conversations/{conversation_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["deleted"])

    def test_stream_chat_endpoint_returns_ndjson_events(self) -> None:
        with self.client.stream(
            "POST",
            "/api/projects/demo/chat/stream",
            json={"query": "请总结一下", "conversation_id": "conv-1"},
        ) as response:
            self.assertEqual(response.status_code, 200)
            events = [json.loads(line) for line in response.iter_lines() if line]

        self.assertEqual([event["type"] for event in events], ["start", "delta", "done"])
        self.assertEqual(self.app_module.pipeline.last_call, ("demo", "请总结一下", "conv-1"))
