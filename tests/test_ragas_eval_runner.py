import json
import math
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
    def test_prepare_samples_reuses_existing_dataset_file(self) -> None:
        from ragas_eval.runner import _prepare_samples

        sample = EvalSample(
            case_id="case-1",
            project_name="存储",
            report_name="报告A.pdf",
            section_path="核心观点",
            question="关键数据是什么？",
            ground_truth="答案",
            reference_contexts=["答案"],
            expected_source_keys=["报告A.pdf|page:2"],
            case_type="factoid",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "auto_cases.jsonl"
            dataset_path.write_text(json.dumps(sample.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")

            with patch("ragas_eval.runner.build_dataset") as build_dataset_mock, patch(
                "ragas_eval.runner.write_dataset_jsonl"
            ) as write_dataset_mock:
                samples = _prepare_samples(
                    projects_dir=Path(tmpdir) / "projects",
                    dataset_path=dataset_path,
                    max_samples=None,
                    force_rebuild=False,
                )

        self.assertEqual([item.case_id for item in samples], ["case-1"])
        build_dataset_mock.assert_not_called()
        write_dataset_mock.assert_not_called()

    def test_prepare_samples_builds_and_writes_dataset_when_file_is_missing(self) -> None:
        from ragas_eval.runner import _prepare_samples

        sample = EvalSample(
            case_id="case-1",
            project_name="存储",
            report_name="报告A.pdf",
            section_path="核心观点",
            question="关键数据是什么？",
            ground_truth="答案",
            reference_contexts=["答案"],
            expected_source_keys=["报告A.pdf|page:2"],
            case_type="factoid",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "auto_cases.jsonl"
            with patch("ragas_eval.runner.build_dataset", return_value=[sample]) as build_dataset_mock, patch(
                "ragas_eval.runner.write_dataset_jsonl"
            ) as write_dataset_mock:
                samples = _prepare_samples(
                    projects_dir=Path(tmpdir) / "projects",
                    dataset_path=dataset_path,
                    max_samples=None,
                    force_rebuild=False,
                )

        self.assertEqual([item.case_id for item in samples], ["case-1"])
        build_dataset_mock.assert_called_once()
        write_dataset_mock.assert_called_once_with([sample], dataset_path)

    def test_prepare_samples_force_rebuild_ignores_existing_dataset_file(self) -> None:
        from ragas_eval.runner import _prepare_samples

        existing = EvalSample(
            case_id="case-old",
            project_name="存储",
            report_name="报告A.pdf",
            section_path="核心观点",
            question="旧问题",
            ground_truth="旧答案",
            reference_contexts=["旧答案"],
            expected_source_keys=["报告A.pdf|page:1"],
            case_type="factoid",
        )
        rebuilt = EvalSample(
            case_id="case-new",
            project_name="存储",
            report_name="报告A.pdf",
            section_path="核心观点",
            question="新问题",
            ground_truth="新答案",
            reference_contexts=["新答案"],
            expected_source_keys=["报告A.pdf|page:2"],
            case_type="factoid",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "auto_cases.jsonl"
            dataset_path.write_text(json.dumps(existing.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8")

            with patch("ragas_eval.runner.build_dataset", return_value=[rebuilt]) as build_dataset_mock, patch(
                "ragas_eval.runner.write_dataset_jsonl"
            ) as write_dataset_mock:
                samples = _prepare_samples(
                    projects_dir=Path(tmpdir) / "projects",
                    dataset_path=dataset_path,
                    max_samples=None,
                    force_rebuild=True,
                )

        self.assertEqual([item.case_id for item in samples], ["case-new"])
        build_dataset_mock.assert_called_once()
        write_dataset_mock.assert_called_once_with([rebuilt], dataset_path)

    def test_ragas_metric_specs_force_answer_relevancy_strictness_to_one(self) -> None:
        from ragas_eval.runner import _ragas_metric_specs

        specs = _ragas_metric_specs()

        self.assertEqual(len(specs), 4)
        self.assertEqual(specs[-1]["class_name"], "AnswerRelevancy")
        self.assertEqual(specs[-1]["kwargs"]["strictness"], 1)

    def test_runner_fails_explicitly_when_ragas_dependency_is_missing(self) -> None:
        from ragas_eval.runner import ensure_ragas_available

        with patch("importlib.import_module", side_effect=ImportError("No module named ragas")):
            with self.assertRaisesRegex(RuntimeError, "ragas dependency is missing"):
                ensure_ragas_available()

    def test_runner_rejects_nan_ragas_summary(self) -> None:
        from ragas_eval.runner import run_evaluation

        sample = EvalSample(
            case_id="case-1",
            project_name="存储",
            report_name="报告A.pdf",
            section_path="核心观点",
            question="关键数据是什么？",
            ground_truth="2025年市场规模达到321亿美元，同比增长37%。",
            reference_contexts=["2025年市场规模达到321亿美元，同比增长37%。"],
            expected_source_keys=["报告A.pdf|page:2"],
            case_type="factoid",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RuntimeError, "RAGAS evaluation produced invalid metrics"):
                run_evaluation(
                    samples=[sample],
                    results_dir=Path(tmpdir) / "results",
                    pipeline=FakePipeline(),
                    ragas_evaluator=lambda rows: {
                        "context_precision": math.nan,
                        "context_recall": 0.9,
                        "faithfulness": 0.85,
                        "answer_relevancy": 0.88,
                    },
                    run_id="demo-run",
                )

    def test_format_ragas_error_explains_free_tier_quota_failures(self) -> None:
        from ragas_eval.runner import _format_ragas_exception

        message = _format_ragas_exception(
            RuntimeError("PermissionDeniedError: AllocationQuota.FreeTierOnly")
        )

        self.assertIn("free tier quota", message)
        self.assertIn("disable the provider's free-tier-only mode", message)

    def test_limit_samples_truncates_dataset_when_requested(self) -> None:
        from ragas_eval.runner import _limit_samples

        samples = [
            EvalSample(
                case_id=f"case-{index}",
                project_name="存储",
                report_name="报告A.pdf",
                section_path="核心观点",
                question=f"问题{index}",
                ground_truth="答案",
                reference_contexts=["答案"],
                expected_source_keys=["报告A.pdf|page:2"],
                case_type="factoid",
            )
            for index in range(5)
        ]

        limited = _limit_samples(samples, 2)

        self.assertEqual([sample.case_id for sample in limited], ["case-0", "case-1"])

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
