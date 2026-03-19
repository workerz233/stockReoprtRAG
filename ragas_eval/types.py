"""Data models for the independent RAGAS evaluation flow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import field


@dataclass(frozen=True)
class EvalSample:
    """One evaluation sample derived from parsed markdown."""

    case_id: str
    project_name: str
    report_name: str
    section_path: str
    question: str
    ground_truth: str
    reference_contexts: list[str]
    expected_source_keys: list[str]
    case_type: str
    should_refuse: bool = False
    expected_answer_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
