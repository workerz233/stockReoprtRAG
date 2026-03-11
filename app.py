"""Application entrypoint for the local research report RAG system."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.conversation_manager import ConversationManager
from backend.file_manager import FileManager
from backend.project_manager import ProjectManager
from backend.rag.pipeline import ResearchRAGPipeline
from config import FRONTEND_DIR, ensure_base_directories

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ensure_base_directories()
project_manager = ProjectManager()
conversation_manager = ConversationManager(project_manager)
pipeline = ResearchRAGPipeline(project_manager, conversation_manager=conversation_manager)
file_manager = FileManager(project_manager=project_manager, pipeline=pipeline)

app = FastAPI(title="Research Report RAG", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


class CreateProjectRequest(BaseModel):
    """Request body for project creation."""

    name: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    """Request body for chat messages."""

    query: str = Field(..., min_length=1)
    conversation_id: str | None = None


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:
    """Return consistent JSON for unexpected errors."""
    logger.exception("Unhandled application error.")
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/")
async def index() -> FileResponse:
    """Serve the frontend entry page."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/projects")
async def list_projects() -> dict[str, list[str]]:
    """List all projects."""
    return {"projects": project_manager.list_projects()}


@app.post("/api/projects")
async def create_project(payload: CreateProjectRequest) -> dict[str, object]:
    """Create a new project."""
    try:
        project = project_manager.create_project(payload.name)
        return {
            "project_name": project.project_name,
            "projects": project_manager.list_projects(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/projects/{project_name}")
async def delete_project(project_name: str) -> dict[str, object]:
    """Delete a whole project and all of its derived artifacts."""
    try:
        result = project_manager.delete_project(project_name)
        result["projects"] = project_manager.list_projects()
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/projects/{project_name}/documents")
async def list_project_documents(project_name: str) -> dict[str, object]:
    """List uploaded PDF documents under a project."""
    try:
        return {
            "project_name": project_name,
            "documents": project_manager.list_project_documents(project_name),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_name}/conversations")
async def list_project_conversations(project_name: str) -> dict[str, object]:
    """List persisted chat conversations under a project."""
    try:
        return {
            "project_name": project_name,
            "conversations": conversation_manager.list_conversations(project_name),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_name}/conversations")
async def create_project_conversation(project_name: str) -> dict[str, object]:
    """Create a new empty chat conversation under a project."""
    try:
        return conversation_manager.create_conversation(project_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_name}/conversations/{conversation_id}")
async def get_project_conversation(project_name: str, conversation_id: str) -> dict[str, object]:
    """Load one persisted chat conversation."""
    try:
        return conversation_manager.get_conversation(project_name, conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/projects/{project_name}/conversations/{conversation_id}")
async def delete_project_conversation(project_name: str, conversation_id: str) -> dict[str, object]:
    """Delete one persisted chat conversation."""
    try:
        return conversation_manager.delete_conversation(project_name, conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/projects/{project_name}/documents/{document_name}")
async def delete_project_document(project_name: str, document_name: str) -> dict[str, object]:
    """Delete an uploaded PDF and its indexed artifacts."""
    try:
        return file_manager.delete_pdf(project_name=project_name, document_name=document_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/projects/{project_name}/upload")
async def upload_pdf(project_name: str, file: UploadFile = File(...)) -> dict[str, object]:
    """Upload and index a PDF under the selected project."""
    try:
        return await file_manager.upload_pdf(project_name=project_name, file=file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/projects/{project_name}/chat")
async def chat(project_name: str, payload: ChatRequest) -> dict[str, object]:
    """Ask a question against a project's indexed reports."""
    try:
        return pipeline.answer_question(
            project_name=project_name,
            query=payload.query,
            conversation_id=payload.conversation_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
