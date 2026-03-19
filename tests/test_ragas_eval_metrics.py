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
            expected_source_keys=["报告A.pdf|page:2"],
            case_type="factoid",
            expected_answer_points=["321亿美元", "37%"],
        )
        response = {
            "answer": "市场规模达到321亿美元。",
            "sources": [
                {"report_name": "报告A.pdf", "section_path": "报告A", "page_no": 2},
                {"report_name": "报告B.pdf", "section_path": "其他章节"},
            ],
        }

        case_result = compute_case_metrics(sample, response, latency_ms=250.0)
        summary = summarize_engineering_metrics([case_result])

        self.assertAlmostEqual(case_result["Recall"], 1.0, places=4)
        self.assertAlmostEqual(case_result["Precision"], 0.5, places=4)
        self.assertAlmostEqual(case_result["F1-score"], 0.6667, places=4)
        self.assertTrue(case_result["Accuracy"])
        self.assertAlmostEqual(case_result["Answer Point Recall"], 0.5, places=4)
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

    def test_case_f1_is_not_penalized_by_fixed_top_k_noise_when_answer_and_hit_are_correct(self) -> None:
        from ragas_eval.metrics import compute_case_metrics

        sample = EvalSample(
            case_id="case-topk",
            project_name="存储",
            report_name="报告A.pdf",
            section_path="核心观点",
            question="关键数据是什么？",
            ground_truth="2025年市场规模达到321亿美元，同比增长37%。",
            reference_contexts=["2025年市场规模达到321亿美元，同比增长37%。"],
            expected_source_keys=["报告A.pdf|page:2"],
            case_type="factoid",
            expected_answer_points=["321亿美元", "37%"],
        )
        response = {
            "answer": "2025年市场规模达到321亿美元，同比增长37%。",
            "sources": [
                {"report_name": "报告A.pdf", "section_path": "报告A", "page_no": 2},
                {"report_name": "报告A.pdf", "section_path": "其他章节1", "page_no": 4},
                {"report_name": "报告A.pdf", "section_path": "其他章节2", "page_no": 5},
                {"report_name": "报告A.pdf", "section_path": "其他章节3", "page_no": 6},
                {"report_name": "报告A.pdf", "section_path": "其他章节4", "page_no": 7},
                {"report_name": "报告A.pdf", "section_path": "其他章节5", "page_no": 8},
                {"report_name": "报告A.pdf", "section_path": "其他章节6", "page_no": 9},
                {"report_name": "报告A.pdf", "section_path": "其他章节7", "page_no": 10},
                {"report_name": "报告A.pdf", "section_path": "其他章节8", "page_no": 11},
                {"report_name": "报告A.pdf", "section_path": "其他章节9", "page_no": 12},
            ],
        }

        case_result = compute_case_metrics(sample, response, latency_ms=200.0)

        self.assertAlmostEqual(case_result["Recall"], 1.0, places=4)
        self.assertAlmostEqual(case_result["Precision"], 1.0, places=4)
        self.assertAlmostEqual(case_result["F1-score"], 1.0, places=4)
        self.assertAlmostEqual(case_result["Answer Point Recall"], 1.0, places=4)
        self.assertTrue(case_result["Accuracy"])

    def test_refusal_case_scores_full_credit_when_model_refuses(self) -> None:
        from ragas_eval.metrics import compute_case_metrics

        sample = EvalSample(
            case_id="case-refusal",
            project_name="存储",
            report_name="报告A.pdf",
            section_path="核心观点",
            question="苹果iPhone销量是多少？",
            ground_truth="未找到足够依据",
            reference_contexts=[],
            expected_source_keys=[],
            case_type="refusal",
            should_refuse=True,
        )
        response = {
            "answer": "未找到足够依据。",
            "sources": [],
        }

        case_result = compute_case_metrics(sample, response, latency_ms=120.0)

        self.assertAlmostEqual(case_result["Recall"], 1.0, places=4)
        self.assertAlmostEqual(case_result["Precision"], 1.0, places=4)
        self.assertAlmostEqual(case_result["F1-score"], 1.0, places=4)
        self.assertIsNone(case_result["Answer Point Recall"])
        self.assertTrue(case_result["Accuracy"])


if __name__ == "__main__":
    unittest.main()
