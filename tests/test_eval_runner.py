import json
import tempfile
import unittest
from pathlib import Path


class EvalRunnerTests(unittest.TestCase):
    def test_evaluate_case_scores_retrieval_and_answer_points(self) -> None:
        from evals.case_generator import EvalCase
        from evals.run_eval import evaluate_case_response

        case = EvalCase(
            project_name="demo",
            question="存储设备推荐哪些公司？",
            expected_reports=["存储设备.pdf"],
            expected_section_keywords=["投资建议"],
            expected_answer_points=["拓荆科技", "京仪装备", "中微公司"],
            should_refuse=False,
            source_type="paragraph",
        )
        response = {
            "answer": "重点推荐拓荆科技、京仪装备、中微公司。",
            "sources": [
                {
                    "report_name": "存储设备.pdf",
                    "section_path": "5 投资建议与风险提示",
                    "page_no": 32,
                    "score": 0.88,
                    "text": "投资建议：重点推荐拓荆科技、京仪装备、中微公司。",
                    "block_type": "paragraph",
                }
            ],
        }

        result = evaluate_case_response(case, response)

        self.assertTrue(result["retrieval_report_hit"])
        self.assertTrue(result["retrieval_section_hit"])
        self.assertEqual(result["answer_point_recall"], 1.0)
        self.assertTrue(result["answer_pass"])

    def test_evaluate_case_response_scores_refusal_cases(self) -> None:
        from evals.case_generator import EvalCase
        from evals.run_eval import evaluate_case_response

        case = EvalCase(
            project_name="demo",
            question="这个项目里的GPU出货量是多少？",
            expected_reports=[],
            expected_section_keywords=[],
            expected_answer_points=[],
            should_refuse=True,
            source_type="synthetic_negative",
        )
        response = {
            "answer": "未找到足够依据。",
            "sources": [],
        }

        result = evaluate_case_response(case, response)

        self.assertTrue(result["refusal_detected"])
        self.assertTrue(result["refusal_correct"])
        self.assertIsNone(result["answer_point_recall"])

    def test_summarize_results_aggregates_metrics(self) -> None:
        from evals.run_eval import summarize_case_results

        summary = summarize_case_results(
            [
                {
                    "retrieval_report_hit": True,
                    "retrieval_section_hit": True,
                    "answer_point_recall": 1.0,
                    "refusal_correct": None,
                },
                {
                    "retrieval_report_hit": False,
                    "retrieval_section_hit": False,
                    "answer_point_recall": 0.5,
                    "refusal_correct": None,
                },
                {
                    "retrieval_report_hit": False,
                    "retrieval_section_hit": False,
                    "answer_point_recall": None,
                    "refusal_correct": True,
                },
            ]
        )

        self.assertEqual(summary["case_count"], 3)
        self.assertAlmostEqual(summary["retrieval_report_hit_rate"], 1 / 3, places=4)
        self.assertAlmostEqual(summary["answer_point_recall_avg"], 0.75, places=4)
        self.assertEqual(summary["refusal_accuracy"], 1.0)

    def test_write_results_json_persists_summary_and_cases(self) -> None:
        from evals.run_eval import write_results_json

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = write_results_json(
                {
                    "summary": {"case_count": 1},
                    "cases": [{"question": "q"}],
                },
                results_dir=Path(temp_dir),
                filename="result.json",
            )

            stored = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["summary"]["case_count"], 1)
            self.assertEqual(stored["cases"][0]["question"], "q")


if __name__ == "__main__":
    unittest.main()
