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
    "资料来源",
    "风险提示",
)
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:%|亿元|亿美元|万片/月|美元|倍|EB)")
LIST_PATTERN = re.compile(r"(?:^|[\n。；：:])\s*(?:重点推荐|推荐|受益标的)[：:\s]*([^。；\n]+)")
SPLIT_PATTERN = re.compile(r"[、，,；;]\s*")
PAGE_PATTERN = re.compile(r"第\s*(\d+)\s*页")
ANCHOR_BAD_PATTERNS = (
    "资料来源",
    "风险提示",
    "股票名称",
    "股票代码",
    "目标价",
    "投资评级",
)
LIST_BAD_PATTERNS = ANCHOR_BAD_PATTERNS + (
    "或覆盖",
    "未覆盖",
    "推荐或覆盖",
)


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

        fact_question = _build_factoid_question(text)
        answer_points = _extract_fact_points(text)
        if fact_question and answer_points:
            answer_points = _extract_fact_points(text)
            samples.append(
                EvalSample(
                    case_id=f"{project_name}-{report_name}-{index}-factoid",
                    project_name=project_name,
                    report_name=report_name,
                    section_path=section_path,
                    question=fact_question,
                    ground_truth=text,
                    reference_contexts=[text],
                    expected_source_keys=_build_expected_source_keys(report_name, section_path),
                    case_type="factoid",
                    expected_answer_points=answer_points,
                )
            )

        list_match = LIST_PATTERN.search(text)
        if list_match:
            items = [
                token.strip()
                for token in SPLIT_PATTERN.split(list_match.group(1))
                if _is_valid_list_item(token.strip())
            ]
            list_question = _build_list_question(text)
            if items:
                samples.append(
                    EvalSample(
                        case_id=f"{project_name}-{report_name}-{index}-list",
                        project_name=project_name,
                        report_name=report_name,
                        section_path=section_path,
                        question=list_question or "报告中的投资建议推荐了哪些标的？",
                        ground_truth="、".join(items),
                        reference_contexts=[text],
                        expected_source_keys=_build_expected_source_keys(report_name, section_path),
                        case_type="list",
                        expected_answer_points=items,
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
                expected_answer_points=list(source.expected_answer_points),
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
    if any(pattern in combined for pattern in LOW_SIGNAL_PATTERNS):
        return True
    if _looks_like_axis_or_table_noise(text):
        return True
    return False


def _build_expected_source_keys(report_name: str, section_path: str) -> list[str]:
    page_no = _extract_page_number(section_path)
    if page_no is not None:
        return [f"{report_name}|page:{page_no}"]
    semantic_section = _strip_page_headings(section_path)
    if semantic_section:
        return [f"{report_name}|{semantic_section}"]
    return [f"{report_name}|{section_path}"]


def _extract_page_number(section_path: str) -> int | None:
    match = PAGE_PATTERN.search(section_path)
    return int(match.group(1)) if match else None


def _strip_page_headings(section_path: str) -> str:
    parts = [part.strip() for part in section_path.split(">")]
    filtered = [part for part in parts if part and not PAGE_PATTERN.fullmatch(part)]
    if len(filtered) >= 2:
        return " > ".join(filtered[1:])
    if filtered:
        return filtered[-1]
    return ""


def _build_factoid_question(text: str) -> str:
    anchor = _extract_anchor(text, drop_numbers=True)
    if anchor:
        return f"报告中关于“{anchor}”的关键数据是什么？"
    return ""


def _build_list_question(text: str) -> str:
    anchor = _extract_anchor(text, drop_numbers=False)
    if anchor:
        return f"报告中关于“{anchor}”推荐了哪些标的？"
    return ""


def _extract_anchor(text: str, *, drop_numbers: bool) -> str:
    sentence = re.split(r"[。；\n]", text.strip(), maxsplit=1)[0].strip()
    sentence = re.sub(r"^(重点推荐|推荐|受益标的)[：:\s]*", "", sentence)
    if drop_numbers:
        sentence = NUMBER_PATTERN.sub("", sentence)
    sentence = re.sub(r"\s+", "", sentence).strip("：:，,、；;。")
    if len(sentence) < 6:
        return ""
    if any(pattern in sentence for pattern in ANCHOR_BAD_PATTERNS):
        return ""
    if re.fullmatch(r"[-+0-9.%]+", sentence):
        return ""
    return sentence[:18]


def _extract_fact_points(text: str) -> list[str]:
    points: list[str] = []
    for sentence in re.split(r"[。；\n]", text):
        normalized = sentence.strip()
        if not normalized:
            continue
        if any(pattern in normalized for pattern in LOW_SIGNAL_PATTERNS):
            continue
        if _looks_like_axis_or_table_noise(normalized):
            continue
        tokens = NUMBER_PATTERN.findall(normalized)
        if not tokens:
            continue
        if len(re.findall(r"[\u4e00-\u9fffA-Za-z]", normalized)) < 6:
            continue
        for token in tokens:
            if token in {"0%", "20%", "40%", "60%", "80%", "100%"} and len(tokens) >= 5:
                continue
            if token not in points:
                points.append(token)
            if len(points) >= 3:
                return points
    return points


def _looks_like_axis_or_table_noise(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return True
    if re.fullmatch(r"[0-9.%+\- ]+", normalized):
        return True
    if sum(1 for _ in NUMBER_PATTERN.finditer(normalized)) >= 5 and len(re.findall(r"[\u4e00-\u9fffA-Za-z]", normalized)) < 8:
        return True
    return False


def _is_valid_list_item(item: str) -> bool:
    if not item or len(item) < 2:
        return False
    if any(pattern in item for pattern in LIST_BAD_PATTERNS):
        return False
    if re.fullmatch(r"[A-Za-z0-9()./ -]+", item):
        return False
    if len(re.findall(r"[\u4e00-\u9fffA-Za-z]", item)) < 2:
        return False
    return True
