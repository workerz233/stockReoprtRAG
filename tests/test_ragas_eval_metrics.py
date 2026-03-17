import unittest

from ragas_eval.types import EvalSample


class RagasEvalMetricsTests(unittest.TestCase):
    def test_summarize_engineering_metrics_returns_recall_accuracy_f1_and_speed(self) -> None:
        from ragas_eval.metrics import compute_case_metrics, summarize_engineering_metrics

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
        response = {
            "answer": "2025年市场规模达到321亿美元，同比增长37%。",
            "sources": [
                {"report_name": "报告A.pdf", "section_path": "核心观点"},
                {"report_name": "报告B.pdf", "section_path": "其他章节"},
            ],
        }

        case_result = compute_case_metrics(sample, response, latency_ms=250.0)
        summary = summarize_engineering_metrics([case_result])

        self.assertAlmostEqual(case_result["Recall"], 1.0, places=4)
        self.assertAlmostEqual(case_result["Precision"], 0.5, places=4)
        self.assertAlmostEqual(case_result["F1-score"], 0.6667, places=4)
        self.assertTrue(case_result["Accuracy"])
        self.assertAlmostEqual(summary["Recall"], 1.0, places=4)
        self.assertAlmostEqual(summary["Accuracy"], 1.0, places=4)
        self.assertAlmostEqual(summary["F1-score"], 0.6667, places=4)
        self.assertEqual(summary["Response Speed"]["avg_ms"], 250.0)

    def test_merge_ragas_and_engineering_metrics_preserves_required_summary_fields(self) -> None:
        from ragas_eval.metrics import summarize_run

        case_results = [
            {
                "Recall": 1.0,
                "Accuracy": True,
                "F1-score": 1.0,
                "latency_ms": 100.0,
            },
            {
                "Recall": 0.0,
                "Accuracy": False,
                "F1-score": 0.0,
                "latency_ms": 300.0,
            },
        ]
        ragas_summary = {
            "context_precision": 0.7,
            "context_recall": 0.6,
            "faithfulness": 0.8,
            "answer_relevancy": 0.9,
        }

        summary = summarize_run(case_results, ragas_summary, dataset_quality={"dataset_insufficient": False})

        self.assertEqual(summary["ragas_metrics"], ragas_summary)
        self.assertAlmostEqual(summary["retrieval_metrics"]["Recall"], 0.5, places=4)
        self.assertAlmostEqual(summary["retrieval_metrics"]["Accuracy"], 0.5, places=4)
        self.assertAlmostEqual(summary["retrieval_metrics"]["F1-score"], 0.5, places=4)
        self.assertEqual(summary["response_speed"]["p50_ms"], 200.0)
        self.assertEqual(summary["dataset_quality"]["dataset_insufficient"], False)


if __name__ == "__main__":
    unittest.main()
