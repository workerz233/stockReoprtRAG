"""Project-scoped conversation persistence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.project_manager import ProjectManager


class ConversationManager:
    """Persist and manage project chat conversations on local disk."""

    def __init__(self, project_manager: ProjectManager) -> None:
        self.project_manager = project_manager

    def list_conversations(self, project_name: str) -> list[dict[str, object]]:
        """List all conversations for a project, newest first."""
        conversations_dir = self._get_conversations_dir(project_name)
        conversations: list[dict[str, object]] = []

        for path in conversations_dir.glob("*.json"):
            conversation = self._load_conversation(path)
            conversations.append(self._build_summary(conversation))

        conversations.sort(key=lambda item: item["updated_at"], reverse=True)
        return conversations

    def create_conversation(self, project_name: str, title: str | None = None) -> dict[str, object]:
        """Create an empty conversation for a project."""
        conversation_id = uuid.uuid4().hex
        now = self._timestamp()
        conversation = {
            "conversation_id": conversation_id,
            "title": title or "新对话",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._write_conversation(project_name, conversation_id, conversation)
        return self._build_summary(conversation)

    def get_conversation(self, project_name: str, conversation_id: str) -> dict[str, object]:
        """Load a persisted conversation."""
        return self._load_conversation(self._get_conversation_path(project_name, conversation_id))

    def append_message(
        self,
        project_name: str,
        conversation_id: str,
        *,
        role: str,
        content: str,
        sources: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        """Append one message to a conversation and persist it."""
        conversation = self.get_conversation(project_name, conversation_id)
        message = {
            "role": role,
            "content": content,
            "created_at": self._timestamp(),
        }
        if sources is not None:
            message["sources"] = sources

        conversation["messages"].append(message)
        conversation["updated_at"] = message["created_at"]

        if conversation["title"] == "新对话" and role == "user":
            conversation["title"] = content.strip()[:30] or "新对话"

        self._write_conversation(project_name, conversation_id, conversation)
        return message

    def delete_conversation(self, project_name: str, conversation_id: str) -> dict[str, object]:
        """Delete a persisted conversation."""
        conversation_path = self._get_conversation_path(project_name, conversation_id)
        if not conversation_path.exists():
            raise FileNotFoundError(f"Conversation not found: {conversation_id}")

        conversation_path.unlink()
        return {
            "project_name": project_name,
            "conversation_id": conversation_id,
            "deleted": True,
        }

    def _get_conversations_dir(self, project_name: str) -> Path:
        project_paths = self.project_manager.get_project_paths(project_name)
        conversations_dir = project_paths.root_dir / "conversations"
        conversations_dir.mkdir(parents=True, exist_ok=True)
        return conversations_dir

    def _get_conversation_path(self, project_name: str, conversation_id: str) -> Path:
        conversation_key = Path(conversation_id).name
        if conversation_key != conversation_id:
            raise ValueError("Conversation id contains unsupported path characters.")

        conversation_path = self._get_conversations_dir(project_name) / f"{conversation_key}.json"
        if not conversation_path.exists():
            raise FileNotFoundError(f"Conversation not found: {conversation_id}")
        return conversation_path

    @staticmethod
    def _build_summary(conversation: dict[str, object]) -> dict[str, object]:
        messages = conversation.get("messages", [])
        return {
            "conversation_id": conversation["conversation_id"],
            "title": conversation.get("title") or "新对话",
            "created_at": conversation["created_at"],
            "updated_at": conversation["updated_at"],
            "message_count": len(messages),
        }

    @staticmethod
    def _load_conversation(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_conversation(
        self,
        project_name: str,
        conversation_id: str,
        conversation: dict[str, object],
    ) -> None:
        conversation_path = self._get_conversations_dir(project_name) / f"{conversation_id}.json"
        conversation_path.write_text(
            json.dumps(conversation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()
