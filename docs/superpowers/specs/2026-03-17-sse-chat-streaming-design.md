# SSE 聊天流式输出设计

**目标**

将当前 `/api/projects/{project_name}/chat` 从同步 JSON 响应改为基于 FastAPI + Uvicorn 的异步 SSE 流式输出，让前端能够边生成边展示回答，并在最后一个事件中附带结构化检索来源。

**范围**

- 保持现有 `POST /api/projects/{project_name}/chat` 路径不变
- 响应类型改为 `text/event-stream`
- 使用异步生成器按 SSE 帧输出回答内容
- 最终事件附带 `sources` 和 `conversation_id`
- 前端改为 `fetch` + SSE 解析，而不是等待完整 JSON
- 保留现有会话持久化能力

**现状**

- `app.py` 当前将 `/chat` 实现为同步 JSON 接口
- `ResearchRAGPipeline.answer_question()` 一次性完成检索、生成、持久化并返回完整字典
- `LLMClient` 只支持非流式 `chat.completions.create()`
- `frontend/app.js` 在发送问题后等待完整 JSON 再渲染消息和来源

**接口设计**

- 请求保持不变：
  - 方法：`POST`
  - Body：`{ "query": "...", "conversation_id": "..." }`
- 响应头：
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
- SSE 事件约定：
  - `event: start`
    - `data`: `{ "conversation_id": "..." }`
  - `event: token`
    - `data`: `{ "delta": "..." }`
  - `event: done`
    - `data`: `{ "answer": "...", "sources": [...], "conversation_id": "..." }`
  - `event: error`
    - `data`: `{ "detail": "..." }`

**数据流**

1. 前端发起 `POST /chat`
2. 后端先解析请求、校验项目和会话
3. Pipeline 先执行检索，构建提示词和历史消息
4. LLM 以流式方式返回增量 token
5. 后端将每个增量包装成 `token` 事件立即输出
6. 流式生成完成后，Pipeline 汇总完整回答，清理模型自带来源段
7. 后端持久化 user/assistant 消息
8. 最后输出 `done` 事件，附上 `answer`、`sources`、`conversation_id`

**检索来源策略**

- `sources` 仍沿用当前结构化字段：
  - `report_name`
  - `section_path`
  - `page_no`
  - `score`
  - `text`
  - `block_type`
- 中间 `token` 事件不携带来源，避免重复发送大 payload
- 只有 `done` 事件带来源，满足“最后一个包附带检索来源”

**异步边界**

- `app.py` 的 `/chat` 使用 `StreamingResponse`
- Pipeline 新增异步流式入口，例如 `stream_answer_question()`
- `LLMClient` 新增流式方法，直接迭代 OpenAI-compatible streaming 响应
- 即使底层 SDK 仍是同步客户端，也通过异步生成器统一 FastAPI 输出方式，保证 Uvicorn 端到端按流发送

**异常与降级**

- 空 query：直接返回 HTTP 400
- 项目或会话不存在：直接返回 HTTP 404 / 400
- 检索为空：
  - 不走 LLM
  - 直接输出 `start` 和 `done`
  - `sources` 为空数组
- LLM 出错：
  - 输出 `error` 事件
  - 不持久化 assistant 成功回答
- 前端解析异常或网络中断：
  - 保留已显示内容
  - 将错误渲染为 assistant 消息提示

**前端渲染策略**

- 用户发送后立刻插入 user 气泡
- 再插入一个 assistant 占位气泡
- 读取 SSE：
  - `start`：更新 `activeConversationId`
  - `token`：累积文本并刷新 assistant 气泡
  - `done`：一次性挂载来源列表并刷新本地会话缓存
  - `error`：显示错误并结束本轮请求

**测试**

- `tests/test_llm_client.py`
  - 验证流式方法能拼出完整文本
  - 验证流式请求会带 `stream=True`
- `tests/test_pipeline_conversations.py`
  - 验证流式 pipeline 输出 token 序列
  - 验证完成后会持久化消息和来源
- `tests/test_api_conversations.py`
  - 验证 `/chat` 返回 `text/event-stream`
  - 验证最后一个事件包含 `sources`

**验收标准**

- 前端能逐步看到回答生成
- `/chat` 使用标准 SSE 帧格式
- 最后一个事件包含完整 `sources`
- 会话 ID 和消息历史仍正常保存
- 无检索结果时也能正确结束 SSE 流
