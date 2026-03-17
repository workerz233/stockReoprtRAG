# RAGAS Eval Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目新增一套旁路旧 `evals/` 的 RAGAS 评测入口，自动构建样本并输出 RAGAS 4 指标以及 `Recall`、`Accuracy`、`F1-score`、`Response Speed`。

**Architecture:** 在 `ragas_eval/` 下建立独立评测单元：数据集构建器负责从真实 `parsed_markdown` 中筛选高质量段落并补充样本，运行器负责调用真实 `ResearchRAGPipeline`、执行 RAGAS 评测并汇总工程指标。实现保持与现有线上链路解耦，不复用旧 `evals/` 代码。

**Tech Stack:** Python 3, pathlib/json/time/statistics, ragas, 现有 RAG pipeline, unittest

---

## Chunk 1: 评测数据模型与样本构建

### Task 1: 为数据模型和 Markdown 筛选规则写失败测试

**Files:**
- Create: `tests/test_ragas_eval_dataset.py`
- Create: `ragas_eval/types.py`
- Create: `ragas_eval/dataset_builder.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_dataset_filters_low_signal_blocks_and_keeps_fact_blocks():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ragas_eval_dataset.py::RagasEvalDatasetTests::test_build_dataset_filters_low_signal_blocks_and_keeps_fact_blocks -v`
Expected: FAIL because `ragas_eval` modules do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class EvalSample:
    case_id: str
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ragas_eval_dataset.py::RagasEvalDatasetTests::test_build_dataset_filters_low_signal_blocks_and_keeps_fact_blocks -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ragas_eval_dataset.py ragas_eval/types.py ragas_eval/dataset_builder.py
git commit -m "feat: add ragas eval dataset builder"
```

### Task 2: 为样本补充和 JSONL 导出写失败测试

**Files:**
- Modify: `tests/test_ragas_eval_dataset.py`
- Modify: `ragas_eval/dataset_builder.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_dataset_adds_followup_and_refusal_samples_when_source_data_is_thin():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ragas_eval_dataset.py::RagasEvalDatasetTests::test_build_dataset_adds_followup_and_refusal_samples_when_source_data_is_thin -v`
Expected: FAIL because supplementation/export behavior is missing.

- [ ] **Step 3: Write minimal implementation**

```python
def write_dataset_jsonl(samples: list[EvalSample], output_path: Path) -> Path:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ragas_eval_dataset.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ragas_eval_dataset.py ragas_eval/dataset_builder.py
git commit -m "feat: add ragas eval dataset supplementation"
```

## Chunk 2: 指标计算与结果汇总

### Task 3: 为 Recall/Accuracy/F1/Speed 计算写失败测试

**Files:**
- Create: `tests/test_ragas_eval_metrics.py`
- Create: `ragas_eval/metrics.py`

- [ ] **Step 1: Write the failing test**

```python
def test_summarize_engineering_metrics_returns_recall_accuracy_f1_and_speed():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ragas_eval_metrics.py::RagasEvalMetricsTests::test_summarize_engineering_metrics_returns_recall_accuracy_f1_and_speed -v`
Expected: FAIL because metrics module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def compute_case_metrics(sample: EvalSample, response: dict[str, object], latency_ms: float) -> dict[str, object]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ragas_eval_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ragas_eval_metrics.py ragas_eval/metrics.py
git commit -m "feat: add ragas eval engineering metrics"
```

### Task 4: 为 RAGAS 结果合并与汇总写失败测试

**Files:**
- Modify: `tests/test_ragas_eval_metrics.py`
- Modify: `ragas_eval/metrics.py`

- [ ] **Step 1: Write the failing test**

```python
def test_merge_ragas_and_engineering_metrics_preserves_required_summary_fields():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ragas_eval_metrics.py::RagasEvalMetricsTests::test_merge_ragas_and_engineering_metrics_preserves_required_summary_fields -v`
Expected: FAIL because merged summary/output schema is incomplete.

- [ ] **Step 3: Write minimal implementation**

```python
def summarize_run(case_results: list[dict[str, object]], ragas_summary: dict[str, float]) -> dict[str, object]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ragas_eval_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ragas_eval_metrics.py ragas_eval/metrics.py
git commit -m "feat: add ragas eval summary schema"
```

## Chunk 3: 运行入口与依赖处理

### Task 5: 为 runner 入口和依赖缺失报错写失败测试

**Files:**
- Create: `tests/test_ragas_eval_runner.py`
- Create: `ragas_eval/runner.py`
- Create: `ragas_eval/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
def test_runner_fails_explicitly_when_ragas_dependency_is_missing():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ragas_eval_runner.py::RagasEvalRunnerTests::test_runner_fails_explicitly_when_ragas_dependency_is_missing -v`
Expected: FAIL because runner does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def main() -> None:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ragas_eval_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_ragas_eval_runner.py ragas_eval/runner.py ragas_eval/__init__.py
git commit -m "feat: add ragas eval runner"
```

### Task 6: 接入真实 pipeline、结果写盘和 README 说明

**Files:**
- Modify: `ragas_eval/runner.py`
- Modify: `README.md`
- Create: `ragas_eval/datasets/.gitkeep`
- Create: `ragas_eval/results/.gitkeep`
- Test: `tests/test_ragas_eval_runner.py`

- [ ] **Step 1: Write the failing test**

```python
def test_runner_writes_summary_and_case_artifacts_with_required_metrics():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ragas_eval_runner.py::RagasEvalRunnerTests::test_runner_writes_summary_and_case_artifacts_with_required_metrics -v`
Expected: FAIL because artifact writing and summary structure are incomplete.

- [ ] **Step 3: Write minimal implementation**

```python
def run_evaluation(...):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ragas_eval_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragas_eval/runner.py README.md ragas_eval/datasets/.gitkeep ragas_eval/results/.gitkeep tests/test_ragas_eval_runner.py
git commit -m "feat: wire ragas eval cli and docs"
```

## Chunk 4: 真实数据烟雾验证

### Task 7: 生成最小真实数据集并执行烟雾验证

**Files:**
- Create: `ragas_eval/datasets/auto_cases.jsonl`
- Create: `ragas_eval/results/<timestamp>/`

- [ ] **Step 1: 运行数据集生成命令**

Run: `python -m ragas_eval.runner --generate-only`
Expected: 生成 `ragas_eval/datasets/auto_cases.jsonl`

- [ ] **Step 2: 运行最小评测命令**

Run: `python -m ragas_eval.runner --dataset ragas_eval/datasets/auto_cases.jsonl`
Expected: 输出 RAGAS 4 指标与 `Recall`、`Accuracy`、`F1-score`、`Response Speed`

- [ ] **Step 3: 验证结果文件结构**

Run: `rg -n '"(context_precision|context_recall|faithfulness|answer_relevancy|Recall|Accuracy|F1-score|Response Speed)"' ragas_eval/results -S`
Expected: 命中 `summary.json` 中的必需字段
