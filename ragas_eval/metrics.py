"""Engineering metrics for the independent RAGAS evaluation flow."""

from __future__ import annotations

from statistics import mean, median

from ragas_eval.types import EvalSample

REFUSAL_PATTERNS = (
    "未找到足够依据",
    "没有足够依据",
    "无法根据当前证据回答",
    "当前项目中还没有可检索内容",
)


def compute_case_metrics(sample: EvalSample, response: dict[str, object], latency_ms: float) -> dict[str, object]:
    """Compute engineering metrics for a single evaluation case."""
    answer = str(response.get("answer", "")).strip()
    sources = response.get("sources", [])
    source_items = [item for item in sources if isinstance(item, dict)] if isinstance(sources, list) else []
    source_keys = {
        f"{str(item.get('report_name', '')).strip()}|{str(item.get('section_path', '')).strip()}"
        for item in source_items
    }
    expected_keys = set(sample.expected_source_keys)
    matched_keys = source_keys & expected_keys

    recall = round(len(matched_keys) / len(expected_keys), 4) if expected_keys else 1.0
    precision = round(len(matched_keys) / len(source_keys), 4) if source_keys else 0.0
    f1_score = _compute_f1(precision, recall)
    refusal_detected = _contains_refusal(answer)
    accuracy = _compute_accuracy(sample, answer, refusal_detected)

    return {
        "case_id": sample.case_id,
        "case_type": sample.case_type,
        "Recall": recall,
        "Precision": precision,
        "F1-score": f1_score,
        "Accuracy": accuracy,
        "latency_ms": round(float(latency_ms), 4),
    }


def summarize_engineering_metrics(case_results: list[dict[str, object]]) -> dict[str, object]:
    """Summarize engineering metrics across all evaluation cases."""
    latencies = [float(result["latency_ms"]) for result in case_results]
    return {
        "Recall": round(mean(float(result["Recall"]) for result in case_results), 4) if case_results else 0.0,
        "Accuracy": round(mean(1.0 if bool(result["Accuracy"]) else 0.0 for result in case_results), 4)
        if case_results
        else 0.0,
        "F1-score": round(mean(float(result["F1-score"]) for result in case_results), 4) if case_results else 0.0,
        "Response Speed": {
            "avg_ms": round(mean(latencies), 4) if latencies else 0.0,
            "p50_ms": round(median(latencies), 4) if latencies else 0.0,
            "p95_ms": round(_percentile(latencies, 0.95), 4) if latencies else 0.0,
        },
    }


def summarize_run(
    case_results: list[dict[str, object]],
    ragas_summary: dict[str, float],
    *,
    dataset_quality: dict[str, object],
) -> dict[str, object]:
    """Build the final summary payload."""
    engineering = summarize_engineering_metrics(case_results)
    return {
        "ragas_metrics": dict(ragas_summary),
        "retrieval_metrics": {
            "Recall": engineering["Recall"],
            "Accuracy": engineering["Accuracy"],
            "F1-score": engineering["F1-score"],
        },
        "response_speed": engineering["Response Speed"],
        "dataset_quality": dict(dataset_quality),
    }


def _compute_accuracy(sample: EvalSample, answer: str, refusal_detected: bool) -> bool:
    normalized_answer = _normalize_text(answer)
    if sample.should_refuse:
        return refusal_detected
    return bool(sample.ground_truth and _normalize_text(sample.ground_truth) in normalized_answer and not refusal_detected)


def _contains_refusal(answer: str) -> bool:
    normalized = _normalize_text(answer)
    return any(pattern in normalized for pattern in REFUSAL_PATTERNS)


def _compute_f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round((2 * precision * recall) / (precision + recall), 4)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _normalize_text(text: str) -> str:
    return "".join(str(text).lower().split())
