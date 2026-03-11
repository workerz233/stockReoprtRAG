"""Chunk structured Markdown blocks with LangChain text splitters."""

from __future__ import annotations

import logging
from dataclasses import dataclass

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    class RecursiveCharacterTextSplitter:  # type: ignore[no-redef]
        """Minimal local fallback when LangChain splitters are unavailable."""

        def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
            self.chunk_size = chunk_size
            self.chunk_overlap = chunk_overlap

        def split_text(self, text: str) -> list[str]:
            normalized_text = text.strip()
            if not normalized_text:
                return []

            chunks: list[str] = []
            start = 0
            text_length = len(normalized_text)
            while start < text_length:
                end = min(start + self.chunk_size, text_length)
                chunks.append(normalized_text[start:end])
                if end >= text_length:
                    break
                start = max(end - self.chunk_overlap, start + 1)
            return chunks

from backend.rag.markdown_processor import MarkdownBlock
from config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkRecord:
    """A chunk ready for embedding and storage."""

    text: str
    section_path: str
    report_name: str
    page_no: int | None
    block_type: str


class DocumentChunker:
    """Use LangChain to split report content into overlapping chunks."""

    def __init__(self) -> None:
        settings = get_settings()
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    def chunk(self, blocks: list[MarkdownBlock], report_name: str) -> list[ChunkRecord]:
        """Split structured blocks while preserving metadata."""
        chunks: list[ChunkRecord] = []
        for block in blocks:
            if not block.text.strip():
                continue

            if block.block_type == "table":
                chunks.append(
                    ChunkRecord(
                        text=block.text,
                        section_path=block.section_path,
                        report_name=report_name,
                        page_no=block.page_no,
                        block_type=block.block_type,
                    )
                )
                continue

            split_texts = self.splitter.split_text(block.text)
            for text in split_texts:
                normalized_text = text.strip()
                if not normalized_text:
                    continue
                chunks.append(
                    ChunkRecord(
                        text=normalized_text,
                        section_path=block.section_path,
                        report_name=report_name,
                        page_no=block.page_no,
                        block_type=block.block_type,
                    )
                )
        logger.info("Generated %s chunks for report %s", len(chunks), report_name)
        return chunks
