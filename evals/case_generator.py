"""Build offline eval cases from existing project markdown files."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

LOW_SIGNAL_PATTERNS = (
    "敬请参阅",
    "扫码获取更多服务",
    "目录",
    "资料来源",
    "图：",
    "图表",
    "分析师预测",
    "相对强于上证指数",
    "股价相对",
    "股票评级",
    "重要法律声明",
)

NEGATIVE_QUESTIONS = (
    "这个项目里的GPU出货量是多少？",
    "这份报告是否披露了苹果iPhone销量？",
)

NUMBER_SENTENCE_PATTERN = re.compile(r"[^。；\n]*\d+(?:\.\d+)?(?:%|亿元|亿美元|万片/月|倍|亿美元)[^。；\n]*")
COMPANY_PATTERN = re.compile(r"(?:重点推荐|推荐)[：:\s]*([^。；\n]+)")
LIST_SPLIT_PATTERN = re.compile(r"[、，,；;]\s*")


@dataclass(frozen=True)
class EvalCase:
    """One offline evaluation sample."""

    project_name: str
    question: str
    expected_reports: list[str]
    expected_section_keywords: list[str]
    expected_answer_points: list[str]
    should_refuse: bool
    source_type: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ParsedBlock:
    """Minimal markdown block used for eval case generation."""

    section_path: str
    text: str
    block_type: str


def build_eval_cases(projects_dir: Path, max_cases_per_project: int = 12) -> list[EvalCase]:
    """Generate a small eval dataset from local project markdown files."""
    projects_path = Path(projects_dir)
    cases: list[EvalCase] = []

    for project_dir in sorted(path for path in projects_path.iterdir() if path.is_dir()):
        project_cases: list[EvalCase] = []
        markdown_root = project_dir / "parsed_markdown"
        if not markdown_root.exists():
            continue

        for markdown_path in sorted(markdown_root.rglob("*.md")):
            if markdown_path.name.endswith(".fallback.md"):
                continue
            markdown_text = markdown_path.read_text(encoding="utf-8")
            report_name = f"{markdown_path.stem}.pdf"
            blocks = parse_markdown_blocks(markdown_text)
            project_cases.extend(_build_positive_cases(project_dir.name, report_name, blocks))
            if len(project_cases) >= max_cases_per_project:
                break

        project_cases = project_cases[:max_cases_per_project]
        project_cases.extend(_build_negative_cases(project_dir.name, project_cases))
        cases.extend(project_cases)

    return cases


def write_cases_jsonl(cases: list[EvalCase], output_path: Path) -> Path:
    """Persist eval cases as JSONL."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(case.to_dict(), ensure_ascii=False) for case in cases) + ("\n" if cases else ""),
        encoding="utf-8",
    )
    return output


def parse_markdown_blocks(markdown_text: str) -> list[ParsedBlock]:
    """Parse headings and paragraphs into minimal eval blocks."""
    blocks: list[ParsedBlock] = []
    heading_stack: dict[int, str] = {}
    paragraph_buffer: list[str] = []

    def current_section_path() -> str:
        ordered_titles = [heading_stack[level] for level in sorted(heading_stack)]
        return " > ".join(title for title in ordered_titles if title) or "未命名章节"

    def flush_paragraph() -> None:
        if not paragraph_buffer:
            return
        text = "\n".join(paragraph_buffer).strip()
        if text:
            blocks.append(
                ParsedBlock(
                    section_path=current_section_path(),
                    text=text,
                    block_type="paragraph",
                )
            )
        paragraph_buffer.clear()

    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            flush_paragraph()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            heading_stack = {depth: value for depth, value in heading_stack.items() if depth < level}
            heading_stack[level] = title
            continue

        paragraph_buffer.append(stripped)

    flush_paragraph()
    return blocks


def _build_positive_cases(
    project_name: str,
    report_name: str,
    blocks: list[object],
) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for block in blocks:
        block_text = getattr(block, "text", "").strip()
        section_path = getattr(block, "section_path", "").strip()
        if not _is_candidate_block(block_text):
            continue

        company_points = _extract_company_points(block_text)
        if company_points:
            cases.append(
                EvalCase(
                    project_name=project_name,
                    question=f"报告在“{section_path}”部分推荐了哪些公司？",
                    expected_reports=[report_name],
                    expected_section_keywords=[section_path, "投资建议"],
                    expected_answer_points=company_points[:4],
                    should_refuse=False,
                    source_type=getattr(block, "block_type", "paragraph"),
                )
            )

        metric_points = _extract_metric_points(block_text)
        if metric_points:
            cases.append(
                EvalCase(
                    project_name=project_name,
                    question=f"报告在“{section_path}”里提到了哪些关键数据？",
                    expected_reports=[report_name],
                    expected_section_keywords=[section_path],
                    expected_answer_points=metric_points[:3],
                    should_refuse=False,
                    source_type=getattr(block, "block_type", "paragraph"),
                )
            )

    return _deduplicate_cases(cases)


def _build_negative_cases(project_name: str, positive_cases: list[EvalCase]) -> list[EvalCase]:
    if not positive_cases:
        return []

    cases: list[EvalCase] = []
    for question in NEGATIVE_QUESTIONS:
        cases.append(
            EvalCase(
                project_name=project_name,
                question=question,
                expected_reports=[],
                expected_section_keywords=[],
                expected_answer_points=[],
                should_refuse=True,
                source_type="synthetic_negative",
            )
        )
    return cases


def _is_candidate_block(text: str) -> bool:
    if len(text) < 20:
        return False
    if any(pattern in text for pattern in LOW_SIGNAL_PATTERNS):
        return False
    return True


def _extract_company_points(text: str) -> list[str]:
    if any(pattern in text for pattern in LOW_SIGNAL_PATTERNS):
        return []

    match = COMPANY_PATTERN.search(text)
    if not match:
        return []

    raw = match.group(1)
    raw = raw.split("受益标的")[0]
    companies = []
    for token in LIST_SPLIT_PATTERN.split(raw):
        cleaned = token.strip(" ：:。.;；")
        if not cleaned or len(cleaned) < 2:
            continue
        companies.append(cleaned)
    return _unique_preserve_order(companies)


def _extract_metric_points(text: str) -> list[str]:
    points = []
    for match in NUMBER_SENTENCE_PATTERN.findall(text):
        cleaned = re.sub(r"\s+", "", match).strip("。；;")
        if len(cleaned) < 6:
            continue
        if any(pattern in cleaned for pattern in LOW_SIGNAL_PATTERNS):
            continue
        if len(re.findall(r"[\u4e00-\u9fffA-Za-z]", cleaned)) < 4:
            continue
        points.append(cleaned)
    return _unique_preserve_order(points)


def _deduplicate_cases(cases: list[EvalCase]) -> list[EvalCase]:
    seen: set[tuple[str, str]] = set()
    deduplicated: list[EvalCase] = []
    for case in cases:
        key = (case.question, "|".join(case.expected_answer_points))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(case)
    return deduplicated


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique_items.append(item)
    return unique_items
