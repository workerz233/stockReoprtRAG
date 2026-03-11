import tempfile
import unittest
from pathlib import Path

from backend.project_manager import ProjectManager
from backend.conversation_manager import ConversationManager


class ConversationManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.project_manager = ProjectManager(projects_dir=Path(self.temp_dir.name))
        self.project_manager.create_project("demo")
        self.manager = ConversationManager(self.project_manager)

    def test_conversation_is_persisted_and_listed(self) -> None:
        conversation = self.manager.create_conversation("demo")
        self.manager.append_message("demo", conversation["conversation_id"], role="user", content="第一问")
        self.manager.append_message(
            "demo",
            conversation["conversation_id"],
            role="assistant",
            content="第一答",
            sources=[{"report_name": "a.pdf", "page_no": 1}],
        )

        conversations = self.manager.list_conversations("demo")

        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["conversation_id"], conversation["conversation_id"])
        self.assertEqual(conversations[0]["message_count"], 2)

        stored = self.manager.get_conversation("demo", conversation["conversation_id"])
        self.assertEqual([message["role"] for message in stored["messages"]], ["user", "assistant"])
        self.assertEqual(
            stored["messages"][1]["sources"],
            [{"report_name": "a.pdf", "page_no": 1}],
        )

    def test_delete_conversation_removes_saved_history(self) -> None:
        conversation = self.manager.create_conversation("demo")
        self.manager.append_message("demo", conversation["conversation_id"], role="user", content="待删除")

        result = self.manager.delete_conversation("demo", conversation["conversation_id"])

        self.assertTrue(result["deleted"])
        with self.assertRaises(FileNotFoundError):
            self.manager.get_conversation("demo", conversation["conversation_id"])


if __name__ == "__main__":
    unittest.main()
