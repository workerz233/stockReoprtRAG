import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ragas_eval.types import EvalSample


class FakePipeline:
    def answer_question(self, project_name: str, question: str) -> dict[str, object]:
        return {
            "answer": "2025年市场规模达到321亿美元，同比增长37%。",
            "sources": [{"report_name": "报告A.pdf", "section_path": "核心观点"}],
            "resolved_query": question,
        }


class RagasEvalRunnerTests(unittest.TestCase):
    def test_runner_fails_explicitly_when_ragas_dependency_is_missing(self) -> None:
        from ragas_eval.runner import ensure_ragas_available

        with patch("importlib.import_module", side_effect=ImportError("No module named ragas")):
            with self.assertRaisesRegex(RuntimeError, "ragas dependency is missing"):
                ensure_ragas_available()

    def test_runner_writes_summary_and_case_artifacts_with_required_metrics(self) -> None:
        from ragas_eval.runner import run_evaluation

        sample = EvalSample(
            case_id="case-1",
            project_name="存储",
            report_name="报告A.pdf",
            section_path="核心观点",
            question="关键数据是什么？",
            ground_truth="2025年市场规模达到321亿美元，同比增长37%。",
            reference_contexts=["2025年市场规模达到321亿美元，同比增长37%。"],
            expected_source_keys=["报告A.pdf|核心观点"],
            case_type="factoid",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            payload = run_evaluation(
                samples=[sample],
                results_dir=results_dir,
                pipeline=FakePipeline(),
                ragas_evaluator=lambda rows: {
                    "context_precision": 0.8,
                    "context_recall": 0.9,
                    "faithfulness": 0.85,
                    "answer_relevancy": 0.88,
                },
                run_id="demo-run",
            )

            summary_path = results_dir / "demo-run" / "summary.json"
            cases_path = results_dir / "demo-run" / "cases.jsonl"

            self.assertTrue(summary_path.exists())
            self.assertTrue(cases_path.exists())

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line]

        self.assertEqual(payload["summary"]["ragas_metrics"]["context_precision"], 0.8)
        self.assertIn("Recall", summary["retrieval_metrics"])
        self.assertIn("Accuracy", summary["retrieval_metrics"])
        self.assertIn("F1-score", summary["retrieval_metrics"])
        self.assertIn("avg_ms", summary["response_speed"])
        self.assertEqual(len(cases), 1)
        self.assertIn("ragas_scores", cases[0])
        self.assertIn("latency_ms", cases[0])


if __name__ == "__main__":
    unittest.main()
