import json
import tempfile
import unittest
from pathlib import Path


class EvalDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.projects_dir = Path(self.temp_dir.name) / "projects"
        markdown_dir = self.projects_dir / "demo" / "parsed_markdown" / "存储设备"
        markdown_dir.mkdir(parents=True, exist_ok=True)
        self.markdown_path = markdown_dir / "存储设备.md"
        self.markdown_path.write_text(
            """# 存储设备

## 1.2 存储价格全面上涨

截至11月10日，DDR4价格较年初涨幅+901%，DDR5价格较年初涨幅+372%。

## 5 投资建议与风险提示

投资建议：重点推荐拓荆科技、京仪装备、中微公司。
风险提示：晶圆厂资本开支不及预期。
""",
            encoding="utf-8",
        )

    def test_build_eval_cases_extracts_positive_and_negative_cases(self) -> None:
        from evals.case_generator import build_eval_cases

        cases = build_eval_cases(self.projects_dir, max_cases_per_project=6)

        self.assertGreaterEqual(len(cases), 3)
        positive_cases = [case for case in cases if not case.should_refuse]
        negative_cases = [case for case in cases if case.should_refuse]
        self.assertTrue(positive_cases)
        self.assertTrue(negative_cases)
        self.assertTrue(any("DDR4" in point for case in positive_cases for point in case.expected_answer_points))
        self.assertTrue(any("投资建议" in keyword for case in positive_cases for keyword in case.expected_section_keywords))
        self.assertTrue(all(case.project_name == "demo" for case in cases))

    def test_write_cases_jsonl_persists_serializable_rows(self) -> None:
        from evals.case_generator import EvalCase, write_cases_jsonl

        output_path = Path(self.temp_dir.name) / "cases.jsonl"
        cases = [
            EvalCase(
                project_name="demo",
                question="存储设备推荐哪些公司？",
                expected_reports=["存储设备.pdf"],
                expected_section_keywords=["投资建议"],
                expected_answer_points=["拓荆科技", "京仪装备", "中微公司"],
                should_refuse=False,
                source_type="paragraph",
            )
        ]

        write_cases_jsonl(cases, output_path)

        rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0]["project_name"], "demo")
        self.assertEqual(rows[0]["expected_answer_points"], ["拓荆科技", "京仪装备", "中微公司"])


if __name__ == "__main__":
    unittest.main()
