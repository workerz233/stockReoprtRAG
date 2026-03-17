# RAGAS 评测设计

**目标**

为本地券商研报 RAG 项目新增一套独立于现有 `evals/` 的 RAGAS 评测能力，直接走真实 `ResearchRAGPipeline`，输出 RAGAS 4 个指标以及 `Recall`、`Accuracy`、`F1-score`、`Response Speed`。

**范围**

- 新增一套旁路旧 `evals/` 的独立评测目录与入口
- 从 `data/projects/*/parsed_markdown/**/*.md` 自动筛选并生成评测样本
- 对样本不足的数据自动补充改写样本与拒答样本
- 直接调用真实检索与生成链路运行评测
- 输出逐样本结果与汇总结果
- 不修改线上 API，不复用旧 `evals/` 代码

**设计**

- 在 `ragas_eval/` 下新增独立评测模块，包括数据集构建、指标计算、评测执行和结果持久化。
- 数据集构建器扫描 `parsed_markdown` 主 Markdown 文件，跳过 `.fallback.md`，解析标题层级与正文块，筛选高信息密度段落。
- 主样本优先覆盖数值事实、推荐列表、比较结论、风险提示等可验证段落，并为每条样本保存 `question`、`ground_truth`、`reference_contexts`、`expected_source_keys`、`case_type`。
- 当某份报告可用样本不足时，自动补充两类样本：基于原文事实的问法改写样本，以及当前项目文档中明确不存在的拒答样本。
- 评测执行器直接实例化现有 `ProjectManager` 与 `ResearchRAGPipeline`，对每条样本调用真实 `answer_question()`，记录 `answer`、`sources`、`resolved_query` 和耗时。
- RAGAS 部分固定输出 `context_precision`、`context_recall`、`faithfulness`、`answer_relevancy` 四个指标。
- 工程侧指标独立计算：`Recall` 基于目标证据召回率，`Accuracy` 基于正样本回答通过率和拒答样本拒答正确率，`F1-score` 基于返回证据的 precision/recall，`Response Speed` 基于样本耗时统计。
- 输出结果写入 `ragas_eval/results/<timestamp>/summary.json` 和 `ragas_eval/results/<timestamp>/cases.jsonl`，并在终端打印摘要。

**数据筛选与补充策略**

- 保留具备唯一来源定位能力的正文块，优先选择具备明确数值、时间、比例、结论、推荐、风险等事实锚点的段落。
- 过滤免责声明、目录、图表目录、分析师信息、低信息密度碎片、严重 OCR 噪声和纯表头残片。
- 同一报告限制重复主题样本数量，避免评测集过度偏向单一模式。
- 若某报告筛选后的正样本不足，先从高质量段落继续挖掘，再基于已有事实生成改写问法；`ground_truth` 和 `reference_contexts` 仍严格来自原文。
- 每个项目固定补充拒答样本，用于评估系统在证据缺失时是否能正确拒答。
- 若总样本量仍低于最小阈值，结果中显式标记 `dataset_insufficient`，而不是使用低质量样本填充。

**指标定义**

- RAGAS 指标：
  - `context_precision`
  - `context_recall`
  - `faithfulness`
  - `answer_relevancy`
- 工程指标：
  - `Recall`：每条样本的 `expected_source_keys` 被返回 `sources` 命中的比例，再对全体样本取平均
  - `Accuracy`：正样本回答通过率与拒答样本拒答正确率汇总后的样本级准确率
  - `F1-score`：以返回证据命中情况计算 precision/recall 后得到的证据级 F1
  - `Response Speed`：每条样本的总耗时，并汇总 `avg`、`p50`、`p95` 与最慢样本

**目录结构**

- `ragas_eval/types.py`：评测数据模型
- `ragas_eval/dataset_builder.py`：Markdown 解析、筛选与样本生成
- `ragas_eval/metrics.py`：工程指标与结果汇总逻辑
- `ragas_eval/runner.py`：CLI、pipeline 调用、RAGAS 执行、结果写入
- `ragas_eval/datasets/`：生成的数据集
- `ragas_eval/results/`：评测结果

**错误处理**

- 当 `ragas` 或所需评审模型依赖缺失时，评测入口直接显式失败并给出缺失项，不回退到旧 `evals/` 或启发式模式。
- 当项目缺少可用 Markdown 或筛选后样本不足时，记录数据质量统计并在汇总中标记。
- 当单条样本调用真实链路失败时，记录错误、保留耗时和输入样本，不中断整个批次。
- 当返回 `sources` 为空、回答为空或链路进入拒答分支时，仍输出完整单样本结果，方便定位问题。

**验证**

- 为数据筛选、样本补充、工程指标计算、结果汇总和运行入口增加单元测试。
- 使用仓库内真实 `parsed_markdown` 数据生成一份最小样本集，执行一次真实评测的烟雾验证。
- 在 `README.md` 中补充新的 RAGAS 评测入口，明确其与旧 `evals/` 隔离。
