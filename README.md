# 本地券商研报 RAG 系统

这是一个完全本地运行的券商研报 RAG 项目，支持多项目管理、PDF 上传、自动解析、向量索引构建，以及 ChatGPT 风格的项目内问答。

系统流程：

`PDF -> MinerU 解析 -> Markdown 结构化 -> 文档切分 -> Ollama Embedding -> Milvus Lite -> 检索 -> OpenAI 兼容 LLM 生成回答`

## 1. 安装依赖

建议使用 Python 3.11+。

本项目按 LangChain 1.x 的分包方式组织依赖，直接使用 `langchain-core` 与 `langchain-text-splitters`，不再依赖旧版聚合包 `langchain`。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

其中 `requirements.txt` 已包含 `pymilvus[milvus_lite]`，用于本地文件版 Milvus Lite。如果你是在旧环境里升级过来的，需要重新执行一次安装命令，确保把 `milvus_lite` 一并装上。

MinerU 建议单独安装并确保命令行可用。当前项目会优先尝试以下命令：

- `magic-pdf`
- `mineru`

如果 MinerU CLI 暂时不可用，系统会回退到 `pypdf` 文本抽取，便于本地联调，但正式解析建议仍使用 MinerU。

## 2. 启动 Ollama Embedding 模型

先确保本机已安装并启动 Ollama，然后拉取 embedding 模型：

```bash
ollama pull qwen3-embedding:0.6b
ollama serve
```

默认 embedding 接口地址为：

`http://localhost:11434/api/embeddings`

## 3. 配置 `.env`

复制示例配置：

```bash
cp .env.example .env
```

示例：

```env
BASE_URL=http://localhost:8001/v1
MODEL_NAME=qwen2.5-7b-instruct
FAST_MODEL_NAME=glm-4.7
LLM_API_KEY=your_api_key
```

说明：

- `BASE_URL` 必须是 OpenAI 兼容服务的根地址，通常形如 `http://host:port/v1`
- `MODEL_NAME` 是最终基于检索证据生成回答时使用的主模型
- `FAST_MODEL_NAME` 是语义路由后的查询改写与澄清追问使用的快模型；未配置时默认回退到 `MODEL_NAME`
- `LLM_API_KEY` 用于远端 OpenAI 兼容服务鉴权；如果你使用本地服务，可以不填，代码会自动回退到 `EMPTY`
- 代码中使用 `python-dotenv` 自动读取 `.env`

## 4. 启动系统

```bash
python app.py
```

启动后访问：

[http://localhost:8000](http://localhost:8000)

## 5. 创建项目

在左侧输入项目名并点击“创建项目”。

项目名支持中文、英文、数字和空格等常见写法；后端会自动为 Milvus 生成安全的 collection 名。

仍然不建议在项目名中使用路径字符，例如 `/`、`\`，也不要使用单独的 `.` 或 `..`。

## 6. 上传研报

在右侧选择 PDF 文件并上传。上传后系统会自动执行：

1. 保存 PDF 到 `data/projects/{project_name}/pdf/`
2. 使用 MinerU 解析 PDF 为 Markdown
3. 解析 Markdown 标题、段落、表格
4. 使用 LangChain 切分文档
5. 调用本地 Ollama 生成向量
6. 写入项目专属的 Milvus Lite 库

问答区支持项目内多会话管理：

- 每个项目下的对话会自动保存到本地
- 下次重新打开页面后，仍可看到之前的历史对话
- 支持新建独立会话、切换历史会话，以及删除单条对话记录

说明：本项目默认使用 Milvus Lite，本地模式下向量索引使用 `FLAT`，以兼容 Lite 的索引限制。

## 7. 提问

在中间聊天区选择项目并提问，例如：

- `宁德时代未来三年的EPS预测是多少？`
- `该研报的投资要点是什么？`
- `公司盈利预测是多少？`

系统会只基于当前项目中已索引的研报内容回答。

聊天入口现在会先经过 `semantic-router` 语义路由，再进入不同执行链路：

- `chitchat`：闲聊，直接走主 LLM，不检索
- `history_qa`：只基于当前会话历史回答
- `history_rewrite_retrieval`：结合历史改写问题后再检索
- `direct_retrieval`：当前问题足够独立，直接检索
- `clarification`：信息不足，直接追问澄清

对于依赖上下文的连续追问，例如：

- `那 2025 年呢？`
- `它的毛利率呢？`
- `和另一篇比呢？`

系统会先由语义路由判断是“可改写后检索”还是“需要先澄清”。前者会先补全成独立检索问题，再进入检索；后者会直接返回追问，避免误检索。

路由样本配置位于：

`config/semantic_routes.json`

当前聊天接口使用 SSE 流式返回。正常回答时，最终 `done` 事件会带上 `resolved_query` 和 `sources`；如果进入澄清分支，最终事件会带空 `sources`，并在 `clarification` 字段中说明澄清问题和原因。

## 8. 离线评测

项目提供了一个离线评测入口，会直接调用真实本地检索链路和真实本地模型。

默认使用 `learn` conda 环境执行，可以直接运行：

```bash
./eval.sh
```

先只生成评测样本：

```bash
./eval.sh --generate-only
```

默认会扫描 `data/projects/*/parsed_markdown/**/*.md`，生成：

`evals/datasets/auto_eval_cases.jsonl`

也可以显式传递参数给底层评测入口：

```bash
./eval.sh --dataset evals/datasets/auto_eval_cases.jsonl
```

评测输出包括：

- 检索命中率：目标报告、目标章节是否进入返回 `sources`
- 回答要点覆盖率：回答中覆盖了多少 `expected_answer_points`
- 拒答准确率：对于应拒答样本，是否正确回答“未找到足够依据”

结果会写入：

`evals/results/<timestamp>.json`

## 9. RAGAS 评测

项目现在还提供一套独立于 `evals/` 的 RAGAS 评测入口，目录位于 `ragas_eval/`，不会复用旧的启发式评测代码。

先只生成数据集：

```bash
python -m ragas_eval.runner --generate-only
```

默认会扫描：

`data/projects/*/parsed_markdown/**/*.md`

生成：

`ragas_eval/datasets/auto_cases.jsonl`

执行完整 RAGAS 评测：

```bash
python -m ragas_eval.runner --dataset ragas_eval/datasets/auto_cases.jsonl
```

评测输出固定包含两组指标：

- RAGAS 4 指标：`context_precision`、`context_recall`、`faithfulness`、`answer_relevancy`
- 工程 4 指标：`Recall`、`Accuracy`、`F1-score`、`Response Speed`

结果会写入：

- `ragas_eval/results/<timestamp>/summary.json`
- `ragas_eval/results/<timestamp>/cases.jsonl`

说明：

- 新评测直接调用真实 `ResearchRAGPipeline`
- 样本从 `parsed_markdown` 自动筛选并补充 followup / refusal 样本
- 若缺少 `ragas`、`datasets` 或 `langchain-openai`，命令会直接报错，不会回退到旧 `evals/`

## 目录结构

```text
research-rag/
  README.md
  requirements.txt
  config.py
  .env.example
  data/
    projects/
  backend/
    project_manager.py
    file_manager.py
    rag/
      mineru_parser.py
      markdown_processor.py
      chunker.py
      embeddings.py
      milvus_store.py
      retriever.py
      llm_client.py
      pipeline.py
  frontend/
    index.html
    app.js
    styles.css
  app.py
```

## 运行说明

- 每个项目都有独立目录：`data/projects/{project_name}`
- PDF 原文件保存于：`pdf/`
- Milvus Lite 数据库存放于：`vector_db/milvus.db`
- 历史对话保存于：`conversations/*.json`
- 系统默认以项目名作为 collection 名称

## 常见问题

### MinerU 未安装怎么办？

系统会记录告警并回退到 `pypdf` 文本抽取，但对表格和复杂版面支持会明显下降。

### 为什么 `.env` 里的 `BASE_URL` 不能直接写到 `/chat/completions`？

因为 OpenAI SDK 需要的是服务根路径，例如：

- 正确：`http://localhost:8001/v1`
- 错误：`http://localhost:8001/v1/chat/completions`

项目中已做了基本兼容清洗，但推荐仍按标准格式配置。
