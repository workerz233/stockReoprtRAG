"""Dataset builder for the independent RAGAS evaluation flow."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ragas_eval.types import EvalSample

LOW_SIGNAL_PATTERNS = (
    "免责声明",
    "目录",
    "图表目录",
    "分析师",
    "请仔细阅读",
    "法律声明",
)
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:%|亿元|亿美元|万片/月|美元|倍|EB)")
LIST_PATTERN = re.compile(r"(?:重点推荐|推荐|受益标的)[：:\s]*([^。；\n]+)")
SPLIT_PATTERN = re.compile(r"[、，,；;]\s*")


def build_dataset(
    projects_dir: Path,
    *,
    min_positive_per_report: int = 4,
    refusal_samples_per_project: int = 2,
) -> list[EvalSample]:
    """Build evaluation samples from parsed markdown."""
    samples: list[EvalSample] = []
    root = Path(projects_dir)
    for project_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        project_positive: list[EvalSample] = []
        markdown_root = project_dir / "parsed_markdown"
        if not markdown_root.exists():
            continue

        for markdown_path in sorted(markdown_root.rglob("*.md")):
            if markdown_path.name.endswith(".fallback.md"):
                continue
            report_name = f"{markdown_path.stem}.pdf"
            blocks = _parse_blocks(markdown_path.read_text(encoding="utf-8"))
            report_positive = _build_positive_samples(project_dir.name, report_name, blocks)
            report_positive = _supplement_followups(report_positive, min_positive_per_report)
            samples.extend(report_positive)
            project_positive.extend(report_positive)

        samples.extend(_build_refusal_samples(project_dir.name, refusal_samples_per_project, project_positive))
    return samples


def write_dataset_jsonl(samples: list[EvalSample], output_path: Path) -> Path:
    """Persist the dataset as JSONL."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.dumps(sample.to_dict(), ensure_ascii=False) for sample in samples]
    output.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    return output


def _parse_blocks(markdown_text: str) -> list[tuple[str, str]]:
    sections: dict[int, str] = {}
    buffer: list[str] = []
    blocks: list[tuple[str, str]] = []

    def current_path() -> str:
        return " > ".join(sections[level] for level in sorted(sections)) or "未命名章节"

    def flush() -> None:
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        if text:
            blocks.append((current_path(), text))
        buffer.clear()

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            sections = {depth: value for depth, value in sections.items() if depth < level}
            sections[level] = title
            continue
        buffer.append(stripped)
    flush()
    return blocks


def _build_positive_samples(project_name: str, report_name: str, blocks: list[tuple[str, str]]) -> list[EvalSample]:
    samples: list[EvalSample] = []
    for index, (section_path, text) in enumerate(blocks, start=1):
        if _is_low_signal(section_path, text):
            continue

        if NUMBER_PATTERN.search(text):
            samples.append(
                EvalSample(
                    case_id=f"{project_name}-{report_name}-{index}-factoid",
                    project_name=project_name,
                    report_name=report_name,
                    section_path=section_path,
                    question=f"报告在“{section_path}”里提到了哪些关键数据？",
                    ground_truth=text,
                    reference_contexts=[text],
                    expected_source_keys=[f"{report_name}|{section_path}"],
                    case_type="factoid",
                )
            )

        list_match = LIST_PATTERN.search(text)
        if list_match:
            items = [token.strip() for token in SPLIT_PATTERN.split(list_match.group(1)) if token.strip()]
            if items:
                samples.append(
                    EvalSample(
                        case_id=f"{project_name}-{report_name}-{index}-list",
                        project_name=project_name,
                        report_name=report_name,
                        section_path=section_path,
                        question=f"报告在“{section_path}”部分推荐了哪些标的？",
                        ground_truth="、".join(items),
                        reference_contexts=[text],
                        expected_source_keys=[f"{report_name}|{section_path}"],
                        case_type="list",
                    )
                )
    return samples


def _supplement_followups(samples: list[EvalSample], min_positive_per_report: int) -> list[EvalSample]:
    supplemented = list(samples)
    seed_samples = [sample for sample in samples if sample.case_type in {"factoid", "list"}]
    cursor = 0
    while supplemented and len(supplemented) < min_positive_per_report:
        source = seed_samples[cursor % len(seed_samples)]
        supplemented.append(
            EvalSample(
                case_id=f"{source.case_id}-followup-{cursor + 1}",
                project_name=source.project_name,
                report_name=source.report_name,
                section_path=source.section_path,
                question="那这一部分具体提到什么？",
                ground_truth=source.ground_truth,
                reference_contexts=list(source.reference_contexts),
                expected_source_keys=list(source.expected_source_keys),
                case_type="followup",
            )
        )
        cursor += 1
    return supplemented


def _build_refusal_samples(
    project_name: str,
    refusal_samples_per_project: int,
    positive_samples: list[EvalSample],
) -> list[EvalSample]:
    if refusal_samples_per_project <= 0 or not positive_samples:
        return []

    questions = (
        "这个项目里的GPU出货量是多少？",
        "这份报告是否披露了苹果iPhone销量？",
        "文档里给出了特斯拉北美销量预测吗？",
    )
    report_name = positive_samples[0].report_name
    section_path = positive_samples[0].section_path
    samples: list[EvalSample] = []
    for index in range(refusal_samples_per_project):
        samples.append(
            EvalSample(
                case_id=f"{project_name}-refusal-{index + 1}",
                project_name=project_name,
                report_name=report_name,
                section_path=section_path,
                question=questions[index % len(questions)],
                ground_truth="未找到足够依据",
                reference_contexts=[],
                expected_source_keys=[],
                case_type="refusal",
                should_refuse=True,
            )
        )
    return samples


def _is_low_signal(section_path: str, text: str) -> bool:
    combined = f"{section_path}\n{text}"
    return any(pattern in combined for pattern in LOW_SIGNAL_PATTERNS)
