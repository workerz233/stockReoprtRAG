"""Project lifecycle management."""

from __future__ import annotations

import logging
import re
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from config import PROJECTS_DIR, ensure_base_directories

logger = logging.getLogger(__name__)

INVALID_PROJECT_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f/\\]")


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved paths for a single project."""

    project_name: str
    collection_name: str
    root_dir: Path
    pdf_dir: Path
    vector_db_dir: Path


class ProjectManager:
    """Manage project directories stored on the local filesystem."""

    def __init__(self, projects_dir: Path = PROJECTS_DIR) -> None:
        ensure_base_directories()
        self.projects_dir = projects_dir

    def create_project(self, name: str) -> ProjectPaths:
        """Create a project directory with PDF and vector DB subdirectories."""
        normalized_name = self._validate_project_name(name)
        project_root = self.projects_dir / normalized_name
        pdf_dir = project_root / "pdf"
        vector_db_dir = project_root / "vector_db"

        if project_root.exists():
            logger.info("Project already exists: %s", normalized_name)
        else:
            logger.info("Creating project: %s", normalized_name)

        pdf_dir.mkdir(parents=True, exist_ok=True)
        vector_db_dir.mkdir(parents=True, exist_ok=True)

        return ProjectPaths(
            project_name=normalized_name,
            collection_name=self._build_collection_name(normalized_name),
            root_dir=project_root,
            pdf_dir=pdf_dir,
            vector_db_dir=vector_db_dir,
        )

    def list_projects(self) -> list[str]:
        """List all existing project names."""
        if not self.projects_dir.exists():
            return []

        projects = sorted(
            path.name for path in self.projects_dir.iterdir() if path.is_dir()
        )
        logger.debug("Listed projects: %s", projects)
        return projects

    def get_project_paths(self, name: str) -> ProjectPaths:
        """Resolve an existing project's paths."""
        normalized_name = self._validate_project_name(name)
        project_root = self.projects_dir / normalized_name
        if not project_root.exists():
            raise FileNotFoundError(f"Project not found: {normalized_name}")

        return ProjectPaths(
            project_name=normalized_name,
            collection_name=self._build_collection_name(normalized_name),
            root_dir=project_root,
            pdf_dir=project_root / "pdf",
            vector_db_dir=project_root / "vector_db",
        )

    def list_project_documents(self, name: str) -> list[str]:
        """List uploaded PDF filenames for a project."""
        project_paths = self.get_project_paths(name)
        if not project_paths.pdf_dir.exists():
            return []

        return sorted(
            path.name
            for path in project_paths.pdf_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )

    def get_project_document_path(self, project_name: str, document_name: str) -> Path:
        """Resolve an existing uploaded PDF path within a project."""
        project_paths = self.get_project_paths(project_name)
        filename = Path(document_name).name
        if filename != document_name:
            raise ValueError("Document name contains unsupported path characters.")

        document_path = project_paths.pdf_dir / filename
        if not document_path.exists() or not document_path.is_file():
            raise FileNotFoundError(f"Document not found: {filename}")
        if document_path.suffix.lower() != ".pdf":
            raise ValueError("Only PDF documents can be managed.")
        return document_path

    def delete_project(self, name: str) -> dict[str, object]:
        """Delete an existing project and all of its artifacts."""
        project_paths = self.get_project_paths(name)

        try:
            shutil.rmtree(project_paths.root_dir)
        except OSError as exc:
            logger.exception("Failed to delete project: %s", project_paths.project_name)
            raise RuntimeError(f"Failed to delete project: {project_paths.project_name}") from exc

        return {
            "project_name": project_paths.project_name,
            "deleted": True,
        }

    def _validate_project_name(self, name: str) -> str:
        """Validate the project name for filesystem safety."""
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Project name cannot be empty.")
        if normalized_name in {".", ".."}:
            raise ValueError(
                "Project name cannot be '.' or '..'."
            )
        if INVALID_PROJECT_NAME_CHARS.search(normalized_name):
            raise ValueError("Project name contains unsupported path characters.")
        return normalized_name

    @staticmethod
    def _build_collection_name(name: str) -> str:
        """Build a Milvus-safe, deterministic collection name from the display name."""
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]
        return f"project_{digest}"
