"""Runner for the independent RAGAS evaluation flow."""

from __future__ import annotations

import argparse
from datetime import datetime
import importlib
import json
import math
from pathlib import Path
import time
from typing import Callable
import warnings

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

    try:
        ragas_summary = dict(ragas_evaluator(ragas_rows))
    except Exception as exc:
        raise RuntimeError(_format_ragas_exception(exc)) from exc
    ragas_summary = _validate_ragas_summary(ragas_summary)
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
    parser.add_argument("--rebuild-dataset", action="store_true")
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    samples = _prepare_samples(
        projects_dir=args.projects_dir,
        dataset_path=args.dataset,
        max_samples=args.max_samples,
        force_rebuild=args.generate_only or args.rebuild_dataset,
    )
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
        from ragas import evaluate
        from langchain_core.embeddings import Embeddings
        from langchain_openai import ChatOpenAI
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
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
        n=1,
    )

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*LangchainLLMWrapper is deprecated.*",
            category=DeprecationWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r".*LangchainEmbeddingsWrapper is deprecated.*",
            category=DeprecationWarning,
        )
        llm = LangchainLLMWrapper(chat_model)
        embeddings = LangchainEmbeddingsWrapper(OllamaLangChainEmbeddings())

    metrics = _build_ragas_metrics()
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


def _prepare_samples(
    *,
    projects_dir: Path,
    dataset_path: Path,
    max_samples: int | None,
    force_rebuild: bool,
) -> list[EvalSample]:
    dataset_file = Path(dataset_path)
    if force_rebuild or not dataset_file.exists():
        samples = build_dataset(projects_dir)
        write_dataset_jsonl(samples, dataset_file)
    else:
        samples = load_dataset_jsonl(dataset_file)
    return _limit_samples(samples, max_samples)


def _limit_samples(samples: list[EvalSample], max_samples: int | None) -> list[EvalSample]:
    if max_samples is None:
        return list(samples)
    if max_samples <= 0:
        raise ValueError("--max-samples must be a positive integer")
    return list(samples[:max_samples])


def _validate_ragas_summary(summary: dict[str, float]) -> dict[str, float]:
    required_metrics = (
        "context_precision",
        "context_recall",
        "faithfulness",
        "answer_relevancy",
    )
    validated: dict[str, float] = {}
    for metric_name in required_metrics:
        raw_value = summary.get(metric_name)
        if not isinstance(raw_value, (int, float)) or not math.isfinite(float(raw_value)):
            raise RuntimeError(
                "RAGAS evaluation produced invalid metrics. Check model quota, provider mode, and rerun."
            )
        validated[metric_name] = round(float(raw_value), 4)
    return validated


def _format_ragas_exception(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "allocationquota.freetieronly" in lowered or "free tier" in lowered:
        return (
            "RAGAS evaluation failed because the provider free tier quota was exhausted. "
            "disable the provider's free-tier-only mode or switch to a paid quota-backed model, then rerun."
        )
    if "permissiondeniederror" in lowered or "403" in lowered:
        return "RAGAS evaluation failed with a provider permission error. Check the model access policy and API key."
    if "enable_thinking" in lowered and "n parameter must be 1" in lowered:
        return "RAGAS evaluation failed because the provider requires n=1 when thinking mode is enabled."
    return f"RAGAS evaluation failed: {message}"


def _build_ragas_metrics() -> list[object]:
    metrics = []
    for spec in _ragas_metric_specs():
        module = importlib.import_module(spec["module_path"])
        metric_class = getattr(module, spec["class_name"])
        metrics.append(metric_class(**spec["kwargs"]))
    return metrics


def _ragas_metric_specs() -> list[dict[str, object]]:
    return [
        {
            "module_path": "ragas.metrics._context_precision",
            "class_name": "ContextPrecision",
            "kwargs": {},
        },
        {
            "module_path": "ragas.metrics._context_recall",
            "class_name": "ContextRecall",
            "kwargs": {},
        },
        {
            "module_path": "ragas.metrics._faithfulness",
            "class_name": "Faithfulness",
            "kwargs": {},
        },
        {
            "module_path": "ragas.metrics._answer_relevance",
            "class_name": "AnswerRelevancy",
            "kwargs": {"strictness": 1},
        },
    ]


if __name__ == "__main__":
    main()
