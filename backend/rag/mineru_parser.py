"""PDF parsing using MinerU CLI with a local fallback."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)


class MinerUParser:
    """Parse PDF files into Markdown using MinerU-compatible CLI tools."""

    _CLI_CANDIDATES: tuple[tuple[str, ...], ...] = (
        ("magic-pdf",),
        ("mineru",),
    )

    def parse_to_markdown(self, pdf_path: Path, output_dir: Path) -> str:
        """Convert a PDF file to Markdown."""
        output_dir.mkdir(parents=True, exist_ok=True)

        for cli in self._CLI_CANDIDATES:
            executable = shutil.which(cli[0])
            if not executable:
                continue

            command = [executable, "-p", str(pdf_path), "-o", str(output_dir)]
            logger.info("Attempting MinerU parse with command: %s", command)
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                markdown = self._read_generated_markdown(output_dir)
                if markdown:
                    return markdown
            except subprocess.CalledProcessError as exc:
                logger.warning("MinerU command failed: %s", exc.stderr.strip())
            except Exception as exc:  # pragma: no cover - depends on external CLI
                logger.warning("Unexpected MinerU parse failure: %s", exc)

        logger.warning("MinerU CLI unavailable or failed. Falling back to pypdf extraction.")
        markdown = self._fallback_markdown(pdf_path)
        fallback_path = output_dir / f"{pdf_path.stem}.fallback.md"
        fallback_path.write_text(markdown, encoding="utf-8")
        return markdown

    @staticmethod
    def _read_generated_markdown(output_dir: Path) -> str:
        """Find the most likely Markdown output from MinerU."""
        markdown_files = sorted(output_dir.rglob("*.md"))
        if not markdown_files:
            return ""
        return markdown_files[0].read_text(encoding="utf-8")

    @staticmethod
    def _fallback_markdown(pdf_path: Path) -> str:
        """Fallback text extraction when MinerU is not available."""
        reader = PdfReader(str(pdf_path))
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"## 第 {index} 页\n\n{text}")

        body = "\n\n".join(pages) if pages else "未能从 PDF 中提取到文本。"
        return f"# {pdf_path.stem}\n\n{body}\n"
