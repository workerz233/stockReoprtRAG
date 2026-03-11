"""File upload and indexing workflow."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from backend.project_manager import ProjectManager
from backend.rag.pipeline import ResearchRAGPipeline

logger = logging.getLogger(__name__)


class FileManager:
    """Manage PDF uploads and trigger downstream indexing."""

    def __init__(
        self,
        project_manager: ProjectManager,
        pipeline: ResearchRAGPipeline,
    ) -> None:
        self.project_manager = project_manager
        self.pipeline = pipeline

    async def upload_pdf(self, project_name: str, file: UploadFile) -> dict[str, object]:
        """Persist a PDF to a project and immediately index it."""
        if not file.filename:
            raise ValueError("Uploaded file must have a filename.")

        suffix = Path(file.filename).suffix.lower()
        if suffix != ".pdf":
            raise ValueError("Only PDF files are supported.")

        project_paths = self.project_manager.get_project_paths(project_name)
        target_path = self._resolve_target_path(project_paths.pdf_dir, file.filename)
        logger.info("Saving PDF to %s", target_path)

        try:
            content = await file.read()
            target_path.write_bytes(content)
        except Exception as exc:  # pragma: no cover - filesystem errors are environment-specific
            logger.exception("Failed to save uploaded file: %s", file.filename)
            raise RuntimeError(f"Failed to save file: {file.filename}") from exc

        indexing_summary = self.pipeline.index_pdf(project_name=project_name, pdf_path=target_path)
        return {
            "project_name": project_name,
            "filename": target_path.name,
            "file_path": str(target_path),
            "indexing": indexing_summary,
        }

    def delete_pdf(self, project_name: str, document_name: str) -> dict[str, object]:
        """Delete a PDF and its downstream indexed artifacts from a project."""
        document_path = self.project_manager.get_project_document_path(project_name, document_name)

        try:
            indexing_cleanup = self.pipeline.delete_report(
                project_name=project_name,
                report_name=document_path.name,
            )
            os.remove(document_path)
        except FileNotFoundError:
            raise
        except Exception as exc:  # pragma: no cover - filesystem/runtime errors are environment-specific
            logger.exception("Failed to delete file: %s", document_name)
            raise RuntimeError(f"Failed to delete file: {document_name}") from exc

        return {
            "project_name": project_name,
            "filename": document_path.name,
            "file_path": str(document_path),
            "deleted": True,
            "indexing_cleanup": indexing_cleanup,
        }

    @staticmethod
    def _resolve_target_path(pdf_dir: Path, original_name: str) -> Path:
        """Prevent accidental overwrite by appending a timestamp when needed."""
        candidate = pdf_dir / Path(original_name).name
        if not candidate.exists():
            return candidate

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        stem = candidate.stem
        suffix = candidate.suffix
        return pdf_dir / f"{stem}_{timestamp}{suffix}"
