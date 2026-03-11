"""Convert structured Markdown into semantic sections."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
PAGE_NUMBER_PATTERNS = (
    re.compile(r"^第\s*(\d+)\s*页$"),
    re.compile(r"^page\s*(\d+)$", re.IGNORECASE),
    re.compile(r"^p\.?\s*(\d+)$", re.IGNORECASE),
)


@dataclass(frozen=True)
class MarkdownBlock:
    """A section extracted from Markdown."""

    section_path: str
    text: str
    block_type: str
    page_no: int | None


class MarkdownProcessor:
    """Parse Markdown into section-aware paragraph and table blocks."""

    def parse(self, markdown_text: str) -> list[MarkdownBlock]:
        """Extract headings, paragraphs, and tables."""
        blocks: list[MarkdownBlock] = []
        heading_stack: dict[int, str] = {}
        current_page_no: int | None = None
        paragraph_buffer: list[str] = []
        table_buffer: list[str] = []

        def current_section_path() -> str:
            ordered_titles = [heading_stack[level] for level in sorted(heading_stack)]
            return " > ".join(title for title in ordered_titles if title) or "未命名章节"

        def flush_paragraph() -> None:
            if not paragraph_buffer:
                return
            text = "\n".join(paragraph_buffer).strip()
            if text:
                blocks.append(
                    MarkdownBlock(
                        section_path=current_section_path(),
                        text=text,
                        block_type="paragraph",
                        page_no=current_page_no,
                    )
                )
            paragraph_buffer.clear()

        def flush_table() -> None:
            if not table_buffer:
                return
            text = "\n".join(table_buffer).strip()
            if text:
                blocks.append(
                    MarkdownBlock(
                        section_path=current_section_path(),
                        text=text,
                        block_type="table",
                        page_no=current_page_no,
                    )
                )
            table_buffer.clear()

        for raw_line in markdown_text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()

            heading_match = HEADING_PATTERN.match(stripped)
            if heading_match:
                flush_paragraph()
                flush_table()
                heading_level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                detected_page = self._extract_page_no(heading_text)
                if detected_page is not None:
                    current_page_no = detected_page
                    continue

                heading_stack = {
                    level: title
                    for level, title in heading_stack.items()
                    if level < heading_level
                }
                heading_stack[heading_level] = heading_text
                continue

            if not stripped:
                flush_paragraph()
                flush_table()
                continue

            detected_page = self._extract_page_no(stripped)
            if detected_page is not None:
                flush_paragraph()
                flush_table()
                current_page_no = detected_page
                continue

            if self._is_table_line(stripped):
                flush_paragraph()
                table_buffer.append(stripped)
                continue

            if table_buffer:
                flush_table()
            paragraph_buffer.append(stripped)

        flush_paragraph()
        flush_table()
        logger.info("Parsed Markdown into %s blocks.", len(blocks))
        return blocks

    @staticmethod
    def _is_table_line(line: str) -> bool:
        """Heuristic for Markdown table rows."""
        return "|" in line and len([segment for segment in line.split("|") if segment.strip()]) >= 2

    @staticmethod
    def _extract_page_no(line: str) -> int | None:
        """Detect page markers emitted by Markdown conversion tools."""
        for pattern in PAGE_NUMBER_PATTERNS:
            match = pattern.match(line)
            if match:
                return int(match.group(1))
        return None
