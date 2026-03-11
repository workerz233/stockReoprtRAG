"""Vector retrieval logic."""

from __future__ import annotations

import math
import logging
import re
from collections import Counter

from backend.project_manager import ProjectManager
from backend.rag.embeddings import OllamaEmbeddingClient
from backend.rag.milvus_store import MilvusStore, SearchResult
from config import get_settings

logger = logging.getLogger(__name__)

LATIN_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
HAN_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")


class MilvusRetriever:
    """Embed queries and retrieve matching chunks from Milvus Lite."""

    def __init__(
        self,
        project_manager: ProjectManager,
        embedding_client: OllamaEmbeddingClient,
    ) -> None:
        self.project_manager = project_manager
        self.embedding_client = embedding_client
        self.settings = get_settings()

    def retrieve(self, project_name: str, query: str) -> list[SearchResult]:
        """Retrieve top-k chunks for a given project and query."""
        project_paths = self.project_manager.get_project_paths(project_name)
        store = MilvusStore(project_paths.vector_db_dir / self.settings.milvus_db_name)
        query_embedding = self.embedding_client.embed_query(query)
        vector_results = store.search(
            collection_name=project_paths.collection_name,
            query_embedding=query_embedding,
            limit=max(self.settings.top_k * 3, self.settings.top_k),
        )
        keyword_results = self._keyword_search(
            query=query,
            candidates=store.list_chunks(project_paths.collection_name),
            limit=max(self.settings.top_k * 3, self.settings.top_k),
        )
        results = self._fuse_results(vector_results=vector_results, keyword_results=keyword_results)
        logger.info("Retrieved %s chunks for project %s", len(results), project_name)
        return results

    def _keyword_search(
        self,
        query: str,
        candidates: list[SearchResult],
        limit: int,
    ) -> list[SearchResult]:
        """Run a lightweight BM25-style lexical ranking over local chunk metadata."""
        if not candidates:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        tokenized_docs = [
            self._tokenize(f"{item.report_name} {item.section_path} {item.text}")
            for item in candidates
        ]
        document_frequencies = Counter()
        for tokens in tokenized_docs:
            document_frequencies.update(set(tokens))

        average_length = sum(len(tokens) for tokens in tokenized_docs) / len(tokenized_docs)
        scored_results: list[SearchResult] = []
        for candidate, tokens in zip(candidates, tokenized_docs, strict=True):
            score = self._bm25_score(
                query_tokens=query_tokens,
                document_tokens=tokens,
                document_frequencies=document_frequencies,
                total_documents=len(tokenized_docs),
                average_length=average_length,
            )
            if score <= 0:
                continue
            scored_results.append(
                SearchResult(
                    text=candidate.text,
                    section_path=candidate.section_path,
                    report_name=candidate.report_name,
                    page_no=candidate.page_no,
                    block_type=candidate.block_type,
                    score=score,
                )
            )

        return sorted(scored_results, key=lambda item: item.score, reverse=True)[:limit]

    def _fuse_results(
        self,
        vector_results: list[SearchResult],
        keyword_results: list[SearchResult],
    ) -> list[SearchResult]:
        """Combine vector and keyword rankings using reciprocal rank fusion."""
        fused: dict[tuple[str, str, int | None, str], dict[str, object]] = {}
        rrf_k = 60

        def apply_rrf(results: list[SearchResult], channel: str, weight: float) -> None:
            for rank, result in enumerate(results, start=1):
                key = (result.report_name, result.section_path, result.page_no, result.text)
                entry = fused.setdefault(
                    key,
                    {
                        "result": result,
                        "score": 0.0,
                        "vector_rank": None,
                        "keyword_rank": None,
                    },
                )
                entry["score"] = float(entry["score"]) + weight * (1.0 / (rrf_k + rank))
                entry[f"{channel}_rank"] = rank

        apply_rrf(vector_results, channel="vector", weight=1.0)
        apply_rrf(keyword_results, channel="keyword", weight=1.0)

        ranked = sorted(
            fused.values(),
            key=lambda entry: (
                -float(entry["score"]),
                entry["keyword_rank"] is None,
                int(entry["keyword_rank"] or 10**9),
                entry["vector_rank"] is None,
                int(entry["vector_rank"] or 10**9),
            ),
        )

        return [
            SearchResult(
                text=entry_result.text,
                section_path=entry_result.section_path,
                report_name=entry_result.report_name,
                page_no=entry_result.page_no,
                block_type=entry_result.block_type,
                score=round(float(entry["score"]), 6),
            )
            for entry in ranked[: self.settings.top_k]
            for entry_result in [entry["result"]]
        ]

    @staticmethod
    def _bm25_score(
        query_tokens: list[str],
        document_tokens: list[str],
        document_frequencies: Counter[str],
        total_documents: int,
        average_length: float,
    ) -> float:
        """Compute a minimal BM25-style score for one document."""
        if not document_tokens or not query_tokens:
            return 0.0

        term_frequencies = Counter(document_tokens)
        k1 = 1.5
        b = 0.75
        document_length = len(document_tokens)
        score = 0.0
        for token in query_tokens:
            frequency = term_frequencies.get(token, 0)
            if frequency == 0:
                continue

            document_frequency = document_frequencies.get(token, 0)
            idf = math.log(1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5))
            denominator = frequency + k1 * (1 - b + b * document_length / max(average_length, 1.0))
            score += idf * (frequency * (k1 + 1) / denominator)
        return score

    @classmethod
    def _tokenize(cls, text: str) -> list[str]:
        """Tokenize mixed Chinese and Latin text for lightweight lexical retrieval."""
        normalized = text.lower()
        tokens = LATIN_TOKEN_PATTERN.findall(normalized)
        for chunk in HAN_TOKEN_PATTERN.findall(normalized):
            if len(chunk) == 1:
                tokens.append(chunk)
                continue
            tokens.extend(chunk[index : index + 2] for index in range(len(chunk) - 1))
        return tokens
