"""Runner for the independent RAGAS evaluation flow."""

from __future__ import annotations

import argparse
from datetime import datetime
import importlib
import json
from pathlib import Path
import time
from typing import Callable

from config import get_settings
from ragas_eval.dataset_builder import build_dataset, write_dataset_jsonl
from ragas_eval.metrics import compute_case_metrics, summarize_run
from ragas_eval.types import EvalSample


def ensure_ragas_available() -> object:
    """Ensure the ragas dependency is importable."""
    try:
        return importlib.import_module("ragas")
    except ImportError as exc:  # pragma: no cover - exercised through mocking in tests
        raise RuntimeError("ragas dependency is missing. Install `ragas` before running this evaluator.") from exc


def run_evaluation(
    *,
    samples: list[EvalSample],
    results_dir: Path,
    pipeline,
    ragas_evaluator: Callable[[list[dict[str, object]]], dict[str, float]],
    run_id: str | None = None,
) -> dict[str, object]:
    """Run the evaluation and write artifacts."""
    case_results: list[dict[str, object]] = []
    ragas_rows: list[dict[str, object]] = []
    for sample in samples:
        started = time.perf_counter()
        response = pipeline.answer_question(sample.project_name, sample.question)
        latency_ms = (time.perf_counter() - started) * 1000
        engineering = compute_case_metrics(sample, response, latency_ms)
        source_items = response.get("sources", [])
        source_contexts = [
            str(item.get("text", "")).strip()
            for item in source_items
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ] if isinstance(source_items, list) else []
        ragas_row = {
            "user_input": sample.question,
            "question": sample.question,
            "answer": response.get("answer", ""),
            "response": response.get("answer", ""),
            "contexts": list(source_contexts),
            "retrieved_contexts": list(source_contexts),
            "ground_truth": sample.ground_truth,
            "reference": sample.ground_truth,
            "reference_contexts": list(sample.reference_contexts),
        }
        ragas_rows.append(ragas_row)
        case_results.append(
            {
                **engineering,
                "project_name": sample.project_name,
                "report_name": sample.report_name,
                "question": sample.question,
                "answer": response.get("answer", ""),
                "sources": response.get("sources", []),
                "ragas_scores": {},
            }
        )

    ragas_summary = dict(ragas_evaluator(ragas_rows))
    for case_result in case_results:
        case_result["ragas_scores"] = dict(ragas_summary)

    summary = summarize_run(
        case_results,
        ragas_summary,
        dataset_quality={
            "dataset_insufficient": len(samples) < 8,
            "dataset_size": len(samples),
        },
    )
    payload = {"summary": summary, "cases": case_results}
    output_dir = Path(results_dir) / (run_id or datetime.now().strftime("%Y%m%d-%H%M%S"))
    _write_results(payload, output_dir)
    return payload


def load_dataset_jsonl(dataset_path: Path) -> list[EvalSample]:
    """Load a JSONL dataset into typed samples."""
    rows = Path(dataset_path).read_text(encoding="utf-8").splitlines()
    return [EvalSample(**json.loads(row)) for row in rows if row.strip()]


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Run the independent RAGAS evaluation flow.")
    parser.add_argument("--projects-dir", type=Path, default=Path("data/projects"))
    parser.add_argument("--dataset", type=Path, default=Path("ragas_eval/datasets/auto_cases.jsonl"))
    parser.add_argument("--results-dir", type=Path, default=Path("ragas_eval/results"))
    parser.add_argument("--generate-only", action="store_true")
    args = parser.parse_args()

    samples = build_dataset(args.projects_dir)
    write_dataset_jsonl(samples, args.dataset)
    if args.generate_only:
        print(f"Generated {len(samples)} samples at {args.dataset}")
        return

    ensure_ragas_available()
    from backend.project_manager import ProjectManager
    from backend.rag.pipeline import ResearchRAGPipeline

    pipeline = ResearchRAGPipeline(ProjectManager(), conversation_manager=None)
    payload = run_evaluation(
        samples=samples,
        results_dir=args.results_dir,
        pipeline=pipeline,
        ragas_evaluator=_evaluate_with_ragas,
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


def _evaluate_with_ragas(rows: list[dict[str, object]]) -> dict[str, float]:
    """Evaluate rows with ragas and return the required summary metrics."""
    ensure_ragas_available()
    try:
        from datasets import Dataset
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("datasets dependency is missing. Install `datasets` before running this evaluator.") from exc
    try:
        from langchain_core.embeddings import Embeddings
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "langchain-openai dependency is missing. Install `langchain-openai` before running this evaluator."
        ) from exc
    try:
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("ragas is installed but required RAGAS modules could not be imported.") from exc

    from backend.rag.embeddings import OllamaEmbeddingClient

    dataset = Dataset.from_list(rows)
    settings = get_settings()

    class OllamaLangChainEmbeddings(Embeddings):
        def __init__(self) -> None:
            self.client = OllamaEmbeddingClient(settings)

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return self.client.embed_documents(texts)

        def embed_query(self, text: str) -> list[float]:
            return self.client.embed_query(text)

    chat_model = ChatOpenAI(
        model=settings.fast_model_name or settings.model_name,
        base_url=settings.base_url,
        api_key=settings.api_key or "EMPTY",
        temperature=0,
    )
    llm = LangchainLLMWrapper(chat_model)
    embeddings = LangchainEmbeddingsWrapper(OllamaLangChainEmbeddings())
    metrics = [context_precision, context_recall, faithfulness, answer_relevancy]
    result = evaluate(dataset=dataset, metrics=metrics, llm=llm, embeddings=embeddings)
    normalized = result.to_pandas().mean(numeric_only=True).to_dict() if hasattr(result, "to_pandas") else dict(result)
    return {
        "context_precision": round(float(normalized.get("context_precision", 0.0)), 4),
        "context_recall": round(float(normalized.get("context_recall", 0.0)), 4),
        "faithfulness": round(float(normalized.get("faithfulness", 0.0)), 4),
        "answer_relevancy": round(float(normalized.get("answer_relevancy", 0.0)), 4),
    }


def _write_results(payload: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    cases_path = output_dir / "cases.jsonl"
    summary_path.write_text(json.dumps(payload["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [json.dumps(case, ensure_ascii=False) for case in payload["cases"]]
    cases_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


if __name__ == "__main__":
    main()
