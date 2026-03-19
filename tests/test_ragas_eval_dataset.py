import json
import tempfile
import unittest
from pathlib import Path


class RagasEvalDatasetTests(unittest.TestCase):
    def test_build_dataset_filters_low_signal_blocks_and_keeps_fact_blocks(self) -> None:
        from ragas_eval.dataset_builder import build_dataset

        with tempfile.TemporaryDirectory() as tmpdir:
            projects_dir = Path(tmpdir) / "projects"
            markdown_dir = projects_dir / "存储" / "parsed_markdown" / "报告A"
            markdown_dir.mkdir(parents=True)
            markdown_dir.joinpath("报告A.md").write_text(
                "\n".join(
                    [
                        "# 报告A",
                        "",
                        "## 第 1 页",
                        "",
                        "目录",
                        "",
                        "## 第 2 页",
                        "",
                        "### 核心观点",
                        "",
                        "AI驱动DRAM需求提升，2025年市场规模达到321亿美元，同比增长37%。",
                    ]
                ),
                encoding="utf-8",
            )

            samples = build_dataset(projects_dir, min_positive_per_report=1, refusal_samples_per_project=0)

        self.assertEqual(len(samples), 1)
        sample = samples[0]
        self.assertEqual(sample.project_name, "存储")
        self.assertEqual(sample.report_name, "报告A.pdf")
        self.assertEqual(sample.case_type, "factoid")
        self.assertIn("321亿美元", sample.ground_truth)
        self.assertIn("page:2", sample.expected_source_keys[0])
        self.assertNotIn("目录", sample.reference_contexts[0])
        self.assertNotRegex(sample.question, r"第\s*2\s*页")

    def test_build_dataset_adds_followup_and_refusal_samples_when_source_data_is_thin(self) -> None:
        from ragas_eval.dataset_builder import build_dataset, write_dataset_jsonl

        with tempfile.TemporaryDirectory() as tmpdir:
            projects_dir = Path(tmpdir) / "projects"
            markdown_dir = projects_dir / "存储" / "parsed_markdown" / "报告A"
            markdown_dir.mkdir(parents=True)
            markdown_dir.joinpath("报告A.md").write_text(
                "\n".join(
                    [
                        "# 报告A",
                        "",
                        "## 投资建议",
                        "",
                        "重点推荐拓荆科技、京仪装备、中微公司。",
                    ]
                ),
                encoding="utf-8",
            )

            samples = build_dataset(projects_dir, min_positive_per_report=3, refusal_samples_per_project=1)
            output_path = Path(tmpdir) / "dataset.jsonl"
            write_dataset_jsonl(samples, output_path)

            written_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line]

        case_types = {sample.case_type for sample in samples}
        self.assertIn("list", case_types)
        self.assertIn("followup", case_types)
        self.assertIn("refusal", case_types)
        self.assertEqual(len(samples), len(written_rows))
        self.assertTrue(any(row["case_type"] == "refusal" for row in written_rows))

    def test_build_dataset_skips_noisy_table_headers_and_source_lines(self) -> None:
        from ragas_eval.dataset_builder import build_dataset

        with tempfile.TemporaryDirectory() as tmpdir:
            projects_dir = Path(tmpdir) / "projects"
            markdown_dir = projects_dir / "存储" / "parsed_markdown" / "报告A"
            markdown_dir.mkdir(parents=True)
            markdown_dir.joinpath("报告A.md").write_text(
                "\n".join(
                    [
                        "# 报告A",
                        "",
                        "## 第 1 页",
                        "",
                        "重点推荐",
                        "股票名称 股票代码 目标价 投资评级",
                        "",
                        "资料来源：各公司官网、华泰研究",
                        "",
                        "0 20% 40% 60% 80% 100%",
                        "",
                        "风险提示：贸易摩擦风险，半导体周期下行风险。",
                    ]
                ),
                encoding="utf-8",
            )

            samples = build_dataset(projects_dir, min_positive_per_report=1, refusal_samples_per_project=0)

        self.assertEqual(samples, [])


if __name__ == "__main__":
    unittest.main()
