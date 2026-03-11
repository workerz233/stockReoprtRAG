"""Milvus Lite storage for per-project vector search."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from pymilvus import DataType, MilvusClient
    from pymilvus.exceptions import ConnectionConfigException
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    DataType = None  # type: ignore[assignment]
    MilvusClient = None  # type: ignore[assignment]

    class ConnectionConfigException(Exception):
        """Fallback placeholder when pymilvus is unavailable."""

from backend.rag.chunker import ChunkRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    """Search result returned from Milvus."""

    text: str
    section_path: str
    report_name: str
    page_no: int | None
    block_type: str
    score: float


class MilvusStore:
    """Persist chunk embeddings into a project-local Milvus Lite database."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if MilvusClient is None:
            logger.warning("pymilvus unavailable, falling back to local JSON vector store.")
            self.client = None
            return
        try:
            self.client = MilvusClient(uri=str(self.db_path))
        except ConnectionConfigException as exc:
            logger.exception("Failed to initialize Milvus Lite client.")
            raise RuntimeError(
                "Milvus Lite is not installed in the current Python environment. "
                "Install it with `pip install -r requirements.txt` or "
                "`pip install 'pymilvus[milvus_lite]>=2.5.4'`."
            ) from exc

    def upsert_chunks(
        self,
        collection_name: str,
        chunks: Sequence[ChunkRecord],
        embeddings: Sequence[Sequence[float]],
    ) -> int:
        """Insert chunks and embeddings into a Milvus collection."""
        if not chunks:
            return 0
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings must have the same length.")

        dimension = len(embeddings[0])
        self.delete_report(collection_name=collection_name, report_name=chunks[0].report_name)

        if self.client is None:
            self._upsert_local_vectors(collection_name=collection_name, chunks=chunks, embeddings=embeddings)
            self._append_lexical_chunks(collection_name=collection_name, chunks=chunks)
            return len(chunks)

        self._ensure_collection(collection_name=collection_name, dimension=dimension)

        entities = [
            {
                "id": self._build_id(chunk),
                "embedding": list(embedding),
                "text": chunk.text,
                "section_path": chunk.section_path,
                "report_name": chunk.report_name,
                "page_no": chunk.page_no if chunk.page_no is not None else -1,
                "block_type": chunk.block_type,
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        logger.info("Inserting %s records into collection %s", len(entities), collection_name)
        try:
            self.client.insert(collection_name=collection_name, data=entities)
        except Exception as exc:
            logger.warning("Insert failed for collection %s, recreating schema: %s", collection_name, exc)
            self._recreate_collection(collection_name=collection_name, dimension=dimension)
            self.client.insert(collection_name=collection_name, data=entities)

        self._append_lexical_chunks(collection_name=collection_name, chunks=chunks)
        return len(entities)

    def search(
        self,
        collection_name: str,
        query_embedding: Sequence[float],
        limit: int = 10,
    ) -> list[SearchResult]:
        """Search the collection for the closest chunks."""
        if self.client is None:
            return self._search_local_vectors(
                collection_name=collection_name,
                query_embedding=query_embedding,
                limit=limit,
            )

        if not self.client.has_collection(collection_name=collection_name):
            return []
        self._ensure_embedding_index(collection_name=collection_name)

        raw_results = self.client.search(
            collection_name=collection_name,
            data=[list(query_embedding)],
            limit=limit,
            output_fields=["text", "section_path", "report_name", "page_no", "block_type"],
        )

        hits = raw_results[0] if raw_results else []
        return [
            SearchResult(
                text=str(hit["entity"].get("text", "")),
                section_path=str(hit["entity"].get("section_path", "")),
                report_name=str(hit["entity"].get("report_name", "")),
                page_no=self._normalize_page_no(hit["entity"].get("page_no")),
                block_type=str(hit["entity"].get("block_type", "paragraph")),
                score=float(hit.get("distance", 0.0)),
            )
            for hit in hits
        ]

    def list_chunks(self, collection_name: str) -> list[SearchResult]:
        """Load locally persisted chunk metadata for lexical retrieval."""
        path = self._lexical_store_path(collection_name)
        if not path.exists():
            return []

        rows = json.loads(path.read_text(encoding="utf-8"))
        return [
            SearchResult(
                text=str(row.get("text", "")),
                section_path=str(row.get("section_path", "")),
                report_name=str(row.get("report_name", "")),
                page_no=self._normalize_page_no(row.get("page_no")),
                block_type=str(row.get("block_type", "paragraph")),
                score=0.0,
            )
            for row in rows
            if str(row.get("text", "")).strip()
        ]

    def delete_report(self, collection_name: str, report_name: str) -> None:
        """Delete existing chunks for the same report before re-indexing."""
        if self.client is not None:
            if not self.client.has_collection(collection_name=collection_name):
                self._remove_report_from_lexical_store(
                    collection_name=collection_name,
                    report_name=report_name,
                )
                self._remove_report_from_local_vectors(
                    collection_name=collection_name,
                    report_name=report_name,
                )
                return

            escaped_report_name = report_name.replace('"', '\\"')
            expression = f'report_name == "{escaped_report_name}"'
            try:
                self.client.delete(collection_name=collection_name, filter=expression)
            except Exception as exc:  # pragma: no cover - depends on Milvus runtime behavior
                logger.warning("Failed to delete existing report rows for %s: %s", report_name, exc)

        self._remove_report_from_local_vectors(
            collection_name=collection_name,
            report_name=report_name,
        )

        self._remove_report_from_lexical_store(
            collection_name=collection_name,
            report_name=report_name,
        )

    def _ensure_collection(self, collection_name: str, dimension: int) -> None:
        """Create the Milvus collection and a Milvus Lite compatible index when absent."""
        if self.client is None:
            return
        if self.client.has_collection(collection_name=collection_name):
            self._ensure_embedding_index(collection_name=collection_name)
            return

        logger.info("Creating Milvus collection %s", collection_name)
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="section_path", datatype=DataType.VARCHAR, max_length=2048)
        schema.add_field(field_name="report_name", datatype=DataType.VARCHAR, max_length=1024)
        schema.add_field(field_name="page_no", datatype=DataType.INT64)
        schema.add_field(field_name="block_type", datatype=DataType.VARCHAR, max_length=32)

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="FLAT",
            metric_type="COSINE",
            params={},
        )

        self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        self._ensure_embedding_index(collection_name=collection_name)

    def _ensure_embedding_index(self, collection_name: str) -> None:
        """Create the embedding index when a collection exists but has no usable index."""
        if self.client is None:
            return
        index_names = self.client.list_indexes(
            collection_name=collection_name,
            field_name="embedding",
        )
        if index_names:
            return

        logger.info("Creating embedding index for collection %s", collection_name)
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="FLAT",
            metric_type="COSINE",
            params={},
        )
        self.client.create_index(
            collection_name=collection_name,
            index_params=index_params,
        )

    def _recreate_collection(self, collection_name: str, dimension: int) -> None:
        """Drop and recreate the collection when stored schema is outdated."""
        if self.client is None:
            return
        if self.client.has_collection(collection_name=collection_name):
            self.client.drop_collection(collection_name=collection_name)
        self._ensure_collection(collection_name=collection_name, dimension=dimension)

    def _append_lexical_chunks(self, collection_name: str, chunks: Sequence[ChunkRecord]) -> None:
        """Persist chunk metadata for local keyword retrieval."""
        path = self._lexical_store_path(collection_name)
        rows = []
        if path.exists():
            rows = json.loads(path.read_text(encoding="utf-8"))

        rows.extend(
            {
                "report_name": chunk.report_name,
                "section_path": chunk.section_path,
                "page_no": chunk.page_no,
                "block_type": chunk.block_type,
                "text": chunk.text,
            }
            for chunk in chunks
        )
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _remove_report_from_lexical_store(self, collection_name: str, report_name: str) -> None:
        """Remove stale chunk metadata for a report."""
        path = self._lexical_store_path(collection_name)
        if not path.exists():
            return

        rows = json.loads(path.read_text(encoding="utf-8"))
        remaining_rows = [row for row in rows if row.get("report_name") != report_name]
        path.write_text(
            json.dumps(remaining_rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _lexical_store_path(self, collection_name: str) -> Path:
        """Return the sidecar metadata path used for keyword retrieval."""
        return self.db_path.with_name(f"{collection_name}_chunks.json")

    def _local_vector_store_path(self, collection_name: str) -> Path:
        """Return the fallback JSON path used when Milvus Lite is unavailable."""
        return self.db_path.with_name(f"{collection_name}_vectors.json")

    def _upsert_local_vectors(
        self,
        collection_name: str,
        chunks: Sequence[ChunkRecord],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Persist vectors in a local JSON file as a Milvus fallback."""
        path = self._local_vector_store_path(collection_name)
        rows = []
        if path.exists():
            rows = json.loads(path.read_text(encoding="utf-8"))

        rows.extend(
            {
                "id": self._build_id(chunk),
                "report_name": chunk.report_name,
                "section_path": chunk.section_path,
                "page_no": chunk.page_no,
                "block_type": chunk.block_type,
                "text": chunk.text,
                "embedding": list(embedding),
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        )
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def _search_local_vectors(
        self,
        collection_name: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[SearchResult]:
        """Run cosine similarity over the local JSON vector fallback."""
        path = self._local_vector_store_path(collection_name)
        if not path.exists():
            return []

        rows = json.loads(path.read_text(encoding="utf-8"))
        scored_rows = []
        for row in rows:
            score = self._cosine_similarity(query_embedding, row.get("embedding", []))
            scored_rows.append((score, row))

        scored_rows.sort(key=lambda item: item[0], reverse=True)
        return [
            SearchResult(
                text=str(row.get("text", "")),
                section_path=str(row.get("section_path", "")),
                report_name=str(row.get("report_name", "")),
                page_no=self._normalize_page_no(row.get("page_no")),
                block_type=str(row.get("block_type", "paragraph")),
                score=float(score),
            )
            for score, row in scored_rows[:limit]
        ]

    def _remove_report_from_local_vectors(self, collection_name: str, report_name: str) -> None:
        """Remove report vectors from the local JSON fallback store."""
        path = self._local_vector_store_path(collection_name)
        if not path.exists():
            return

        rows = json.loads(path.read_text(encoding="utf-8"))
        remaining_rows = [row for row in rows if row.get("report_name") != report_name]
        path.write_text(json.dumps(remaining_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_page_no(raw_page_no: object) -> int | None:
        """Map persisted page markers to nullable integers."""
        if raw_page_no in (None, "", -1):
            return None
        return int(raw_page_no)

    @staticmethod
    def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
        """Compute cosine similarity for the local vector-store fallback."""
        if not left or not right or len(left) != len(right):
            return 0.0

        numerator = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(float(value) * float(value) for value in left))
        right_norm = math.sqrt(sum(float(value) * float(value) for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _build_id(chunk: ChunkRecord) -> str:
        """Generate a stable primary key for a chunk."""
        raw = (
            f"{chunk.report_name}:{chunk.section_path}:{chunk.page_no}:"
            f"{chunk.block_type}:{chunk.text}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]
