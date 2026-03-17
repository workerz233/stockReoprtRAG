"""End-to-end RAG indexing and answering pipeline."""

from __future__ import annotations

from collections.abc import AsyncIterator
import logging
import re
import shutil
from pathlib import Path

from backend.conversation_manager import ConversationManager
from backend.project_manager import ProjectManager
from backend.rag.chunker import DocumentChunker
from backend.rag.embeddings import OllamaEmbeddingClient
from backend.rag.llm_client import LLMClient
from backend.rag.markdown_processor import MarkdownProcessor
from backend.rag.milvus_store import MilvusStore
from backend.rag.mineru_parser import MinerUParser
from backend.rag.retriever import MilvusRetriever
from config import get_settings

logger = logging.getLogger(__name__)

SOURCE_SECTION_PATTERN = re.compile(
    r"(?:\n\s*[-*_]{3,}\s*)?\n\s*(?:#+\s*)?\*{0,2}引用来源\*{0,2}\s*(?:\n|$)",
    re.IGNORECASE,
)

PROMPT_TEMPLATE = """你将收到若干条检索证据。你必须严格遵守以下规则：
1. 只能基于“检索证据”回答，不能使用外部知识或猜测。
2. 如果证据不能直接支持问题，必须直接回答：未找到足够依据。
3. 回答尽量简洁、事实化，引用数字或结论时必须有对应证据。
4. 不要在回答中附加“引用来源”、来源列表、页码表格或证据清单；系统会单独展示来源。

检索证据：
{retrieved_chunks}

问题：
{query}

请用中文回答。
"""


class ResearchRAGPipeline:
    """Coordinate report parsing, vectorization, retrieval, and answer generation."""

    def __init__(
        self,
        project_manager: ProjectManager,
        conversation_manager: ConversationManager | None = None,
    ) -> None:
        self.project_manager = project_manager
        self.conversation_manager = conversation_manager
        self.settings = get_settings()
        self.parser = MinerUParser()
        self.processor = MarkdownProcessor()
        self.chunker = DocumentChunker()
        self.embedding_client = OllamaEmbeddingClient(self.settings)
        self.retriever = MilvusRetriever(project_manager, self.embedding_client)
        self.llm_client = LLMClient(self.settings)

    def index_pdf(self, project_name: str, pdf_path: Path) -> dict[str, object]:
        """Parse and index a PDF into the project's Milvus Lite store."""
        project_paths = self.project_manager.get_project_paths(project_name)
        markdown_dir = project_paths.root_dir / "parsed_markdown" / pdf_path.stem
        markdown_text = self.parser.parse_to_markdown(pdf_path=pdf_path, output_dir=markdown_dir)

        blocks = self.processor.parse(markdown_text)
        if not blocks:
            raise RuntimeError(f"No structured content extracted from {pdf_path.name}.")

        chunks = self.chunker.chunk(blocks=blocks, report_name=pdf_path.name)
        if not chunks:
            raise RuntimeError(f"No chunks generated for {pdf_path.name}.")

        embeddings = self.embedding_client.embed_documents([chunk.text for chunk in chunks])
        store = MilvusStore(project_paths.vector_db_dir / self.settings.milvus_db_name)
        inserted = store.upsert_chunks(
            collection_name=project_paths.collection_name,
            chunks=chunks,
            embeddings=embeddings,
        )

        markdown_output = markdown_dir / f"{pdf_path.stem}.md"
        if not markdown_output.exists():
            markdown_output.write_text(markdown_text, encoding="utf-8")

        summary = {
            "report_name": pdf_path.name,
            "markdown_path": str(markdown_output),
            "blocks": len(blocks),
            "chunks": len(chunks),
            "inserted_records": inserted,
        }
        logger.info("Indexed PDF summary: %s", summary)
        return summary

    def answer_question(
        self,
        project_name: str,
        query: str,
        conversation_id: str | None = None,
    ) -> dict[str, object]:
        """Retrieve relevant chunks and ask the local LLM to answer."""
        query = query.strip()
        if not query:
            raise ValueError("Query cannot be empty.")

        conversation_id = self._resolve_conversation_id(project_name, conversation_id)
        history_messages = self._build_history_messages(project_name, conversation_id)

        results = self.retriever.retrieve(project_name=project_name, query=query)
        if not results:
            answer = "当前项目中还没有可检索内容，请先上传并索引研报 PDF。"
            sources: list[dict[str, object]] = []
        else:
            prompt = self._build_prompt(query=query, results=results)
            answer = self._strip_source_section(
                self.llm_client.answer_messages([*history_messages, {"role": "user", "content": prompt}])
            )
            sources = self._build_sources(results)

        self._persist_conversation_turn(
            project_name=project_name,
            conversation_id=conversation_id,
            query=query,
            answer=answer,
            sources=sources,
        )

        response = {
            "answer": answer,
            "sources": sources,
        }
        if conversation_id:
            response["conversation_id"] = conversation_id
        return response

    async def stream_answer_question(
        self,
        project_name: str,
        query: str,
        conversation_id: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Retrieve relevant chunks and stream the answer as structured events."""
        query = query.strip()
        if not query:
            raise ValueError("Query cannot be empty.")

        conversation_id = self._resolve_conversation_id(project_name, conversation_id)
        yield {"type": "start", "conversation_id": conversation_id}

        results = self.retriever.retrieve(project_name=project_name, query=query)
        sources = self._build_sources(results)
        if not results:
            answer = "当前项目中还没有可检索内容，请先上传并索引研报 PDF。"
            self._persist_conversation_turn(
                project_name=project_name,
                conversation_id=conversation_id,
                query=query,
                answer=answer,
                sources=sources,
            )
            yield {
                "type": "done",
                "answer": answer,
                "sources": sources,
                "conversation_id": conversation_id,
            }
            return

        prompt = self._build_prompt(query=query, results=results)
        history_messages = self._build_history_messages(project_name, conversation_id)
        chunks: list[str] = []
        async for delta in self.llm_client.stream_answer_messages(
            [*history_messages, {"role": "user", "content": prompt}]
        ):
            chunks.append(delta)
            yield {"type": "token", "delta": delta, "conversation_id": conversation_id}

        answer = self._strip_source_section("".join(chunks)) or "未生成有效回答。"
        self._persist_conversation_turn(
            project_name=project_name,
            conversation_id=conversation_id,
            query=query,
            answer=answer,
            sources=sources,
        )
        yield {
            "type": "done",
            "answer": answer,
            "sources": sources,
            "conversation_id": conversation_id,
        }

    def delete_report(self, project_name: str, report_name: str) -> dict[str, object]:
        """Delete a report's vectors and parsed markdown artifacts."""
        project_paths = self.project_manager.get_project_paths(project_name)
        store = MilvusStore(project_paths.vector_db_dir / self.settings.milvus_db_name)
        store.delete_report(
            collection_name=project_paths.collection_name,
            report_name=report_name,
        )

        markdown_dir = project_paths.root_dir / "parsed_markdown" / Path(report_name).stem
        markdown_removed = False
        if markdown_dir.exists():
            shutil.rmtree(markdown_dir)
            markdown_removed = True

        return {
            "report_name": report_name,
            "markdown_removed": markdown_removed,
        }

    @staticmethod
    def _format_page_no(page_no: int | None) -> str:
        """Render nullable page numbers consistently for prompts."""
        return f"第 {page_no} 页" if page_no is not None else "未知页码"

    @staticmethod
    def _strip_source_section(answer: str) -> str:
        """Remove model-emitted source sections; the UI renders structured sources separately."""
        match = SOURCE_SECTION_PATTERN.search(answer)
        if not match:
            return answer.strip()
        return answer[: match.start()].rstrip()

    def _resolve_conversation_id(self, project_name: str, conversation_id: str | None) -> str | None:
        if self.conversation_manager is None:
            return None
        if conversation_id:
            self.conversation_manager.get_conversation(project_name, conversation_id)
            return conversation_id
        return self.conversation_manager.create_conversation(project_name)["conversation_id"]

    def _build_history_messages(
        self,
        project_name: str,
        conversation_id: str | None,
    ) -> list[dict[str, str]]:
        if self.conversation_manager is None or not conversation_id:
            return []

        conversation = self.conversation_manager.get_conversation(project_name, conversation_id)
        raw_messages = conversation.get("messages", [])
        max_messages = getattr(self.settings, "conversation_history_messages", 8)
        if max_messages > 0:
            raw_messages = raw_messages[-max_messages:]

        history_messages = []
        for message in raw_messages:
            role = message.get("role")
            content = message.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                history_messages.append({"role": role, "content": content})
        return history_messages

    def _build_prompt(self, query: str, results: list[object]) -> str:
        context = "\n\n".join(
            [
                (
                    f"[证据{index}] 报告名: {result.report_name}\n"
                    f"章节路径: {result.section_path or '未命名章节'}\n"
                    f"页码: {self._format_page_no(result.page_no)}\n"
                    f"块类型: {result.block_type}\n"
                    f"内容: {result.text}"
                )
                for index, result in enumerate(results, start=1)
            ]
        )
        return PROMPT_TEMPLATE.format(retrieved_chunks=context, query=query)

    @staticmethod
    def _build_sources(results: list[object]) -> list[dict[str, object]]:
        return [
            {
                "report_name": result.report_name,
                "section_path": result.section_path,
                "page_no": result.page_no,
                "score": result.score,
                "text": result.text,
                "block_type": result.block_type,
            }
            for result in results
        ]

    def _persist_conversation_turn(
        self,
        *,
        project_name: str,
        conversation_id: str | None,
        query: str,
        answer: str,
        sources: list[dict[str, object]],
    ) -> None:
        if self.conversation_manager is None or not conversation_id:
            return

        self.conversation_manager.append_message(
            project_name,
            conversation_id,
            role="user",
            content=query,
        )
        self.conversation_manager.append_message(
            project_name,
            conversation_id,
            role="assistant",
            content=answer,
            sources=sources,
        )
