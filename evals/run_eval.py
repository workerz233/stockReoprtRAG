"""Run offline evaluation against the real local RAG pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import TYPE_CHECKING

from evals.case_generator import EvalCase, build_eval_cases, write_cases_jsonl

if TYPE_CHECKING:
    from backend.project_manager import ProjectManager
    from backend.rag.pipeline import ResearchRAGPipeline

REFUSAL_PATTERNS = (
    "未找到足够依据",
    "没有足够依据",
    "没有可支持证据",
    "无法根据当前证据回答",
    "当前项目中还没有可检索内容",
)


def evaluate_case_response(case: EvalCase, response: dict[str, object]) -> dict[str, object]:
    """Score retrieval and answer quality for a single case."""
    answer = str(response.get("answer", "")).strip()
    sources = response.get("sources", [])
    source_items = sources if isinstance(sources, list) else []

    retrieval_report_hit = any(
        source.get("report_name") in case.expected_reports
        for source in source_items
        if isinstance(source, dict)
    )
    retrieval_section_hit = any(
        any(keyword and keyword in str(source.get("section_path", "")) for keyword in case.expected_section_keywords)
        for source in source_items
        if isinstance(source, dict)
    )

    refusal_detected = _contains_refusal(answer)
    if case.should_refuse:
        answer_point_recall = None
        answer_pass = refusal_detected
        refusal_correct = refusal_detected
    else:
        answer_point_recall = _compute_answer_point_recall(answer, case.expected_answer_points)
        answer_pass = answer_point_recall >= 0.6 and not refusal_detected
        refusal_correct = None

    return {
        "question": case.question,
        "project_name": case.project_name,
        "should_refuse": case.should_refuse,
        "answer": answer,
        "sources": source_items,
        "retrieval_report_hit": retrieval_report_hit,
        "retrieval_section_hit": retrieval_section_hit,
        "answer_point_recall": answer_point_recall,
        "answer_pass": answer_pass,
        "refusal_detected": refusal_detected,
        "refusal_correct": refusal_correct,
    }


def summarize_case_results(case_results: list[dict[str, object]]) -> dict[str, object]:
    """Aggregate case-level metrics."""
    answer_point_scores = [
        float(result["answer_point_recall"])
        for result in case_results
        if result.get("answer_point_recall") is not None
    ]
    refusal_scores = [
        bool(result["refusal_correct"])
        for result in case_results
        if result.get("refusal_correct") is not None
    ]

    return {
        "case_count": len(case_results),
        "retrieval_report_hit_rate": _average_bool(bool(result.get("retrieval_report_hit")) for result in case_results),
        "retrieval_section_hit_rate": _average_bool(bool(result.get("retrieval_section_hit")) for result in case_results),
        "answer_point_recall_avg": round(mean(answer_point_scores), 4) if answer_point_scores else None,
        "refusal_accuracy": round(mean(1.0 if score else 0.0 for score in refusal_scores), 4) if refusal_scores else None,
        "answer_pass_rate": _average_bool(bool(result.get("answer_pass")) for result in case_results),
    }


def write_results_json(payload: dict[str, object], results_dir: Path, filename: str | None = None) -> Path:
    """Persist eval output as a JSON artifact."""
    output_dir = Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = filename or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    output_path = output_dir / output_name
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def load_cases_jsonl(dataset_path: Path) -> list[EvalCase]:
    """Load eval cases from JSONL."""
    rows = Path(dataset_path).read_text(encoding="utf-8").splitlines()
    return [EvalCase(**json.loads(row)) for row in rows if row.strip()]


def run_eval_dataset(
    dataset_path: Path,
    *,
    project_manager: "ProjectManager | None" = None,
    pipeline: "ResearchRAGPipeline | None" = None,
) -> dict[str, object]:
    """Run eval cases against the real pipeline."""
    from backend.project_manager import ProjectManager
    from backend.rag.pipeline import ResearchRAGPipeline

    cases = load_cases_jsonl(dataset_path)
    manager = project_manager or ProjectManager()
    rag_pipeline = pipeline or ResearchRAGPipeline(manager, conversation_manager=None)

    results = []
    for case in cases:
        try:
            response = rag_pipeline.answer_question(case.project_name, case.question)
            result = evaluate_case_response(case, response)
        except Exception as exc:  # pragma: no cover - runtime safety for local evals
            result = {
                **asdict(case),
                "answer": "",
                "sources": [],
                "retrieval_report_hit": False,
                "retrieval_section_hit": False,
                "answer_point_recall": None,
                "answer_pass": False,
                "refusal_detected": False,
                "refusal_correct": False if case.should_refuse else None,
                "error": str(exc),
            }
        results.append(result)

    return {
        "summary": summarize_case_results(results),
        "cases": results,
    }


def main() -> None:
    """CLI for dataset generation and evaluation."""
    parser = argparse.ArgumentParser(description="Run offline eval for the local RAG project.")
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets/auto_eval_cases.jsonl"))
    parser.add_argument("--projects-dir", type=Path, default=Path("data/projects"))
    parser.add_argument("--results-dir", type=Path, default=Path("evals/results"))
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--max-cases-per-project", type=int, default=12)
    args = parser.parse_args()

    if not args.dataset.exists():
        cases = build_eval_cases(args.projects_dir, max_cases_per_project=args.max_cases_per_project)
        write_cases_jsonl(cases, args.dataset)
        print(f"Generated {len(cases)} eval cases at {args.dataset}")
        if args.generate_only:
            return

    if args.generate_only:
        cases = build_eval_cases(args.projects_dir, max_cases_per_project=args.max_cases_per_project)
        write_cases_jsonl(cases, args.dataset)
        print(f"Generated {len(cases)} eval cases at {args.dataset}")
        return

    payload = run_eval_dataset(args.dataset)
    output_path = write_results_json(payload, args.results_dir)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"Saved eval results to {output_path}")


def _contains_refusal(answer: str) -> bool:
    normalized = _normalize_text(answer)
    return any(pattern in normalized for pattern in REFUSAL_PATTERNS)


def _compute_answer_point_recall(answer: str, expected_points: list[str]) -> float:
    if not expected_points:
        return 1.0

    normalized_answer = _normalize_text(answer)
    hits = sum(1 for point in expected_points if _normalize_text(point) in normalized_answer)
    return round(hits / len(expected_points), 4)


def _average_bool(values) -> float | None:
    values = list(values)
    if not values:
        return None
    return round(mean(1.0 if value else 0.0 for value in values), 4)


def _normalize_text(text: str) -> str:
    return "".join(str(text).lower().split())


if __name__ == "__main__":
    main()
