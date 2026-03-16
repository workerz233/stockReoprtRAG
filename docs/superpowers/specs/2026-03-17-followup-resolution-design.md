# 追问识别与指代补全设计

**目标**

为当前研报 RAG 项目增加一层检索前的“追问识别 + 指代补全 + 澄清分流”能力，在用户问题进入向量化和向量库检索之前，先判断它是否依赖最近几轮对话上下文，并在高置信度时自动改写为可独立检索的问题。

**范围**

- 在现有 `/api/projects/{project_name}/chat` 链路中加入前置追问解析模块
- 支持最近 `N` 轮对话内的追问识别与省略指代补全
- 在高置信度时自动改写问题并进入现有检索链路
- 在低置信度或存在多解释时返回澄清问题，而不是强行检索
- 引入 `FAST_MODEL_NAME` 作为前置识别专用快模型
- 不修改现有向量检索算法本身
- 不在本期扩展到“列文档/删文档/项目操作”等其他意图识别

**现状**

- 当前用户问题从 `app.py` 的 `/chat` 入口直接进入 `ResearchRAGPipeline.answer_question()`
- `answer_question()` 直接调用 `MilvusRetriever.retrieve()`，随后将召回结果交给主模型回答
- 会话上下文当前只用于把历史消息拼进最终回答模型输入，不参与检索前的问题判定或改写
- 目前没有任何“追问/省略指代”专门处理逻辑

**设计**

- 新增 `FollowupResolver` 模块，职责是根据“当前问题 + 最近 N 轮对话”输出结构化追问判定结果
- `FollowupResolver` 使用 `FAST_MODEL_NAME` 对问题做快速结构化分析，不参与最终回答生成
- 现有主模型 `MODEL_NAME` 继续负责基于检索证据生成最终回答
- `ResearchRAGPipeline.answer_question()` 负责调度：
  - 读取会话历史
  - 调用 `FollowupResolver`
  - 根据结果决定使用原问题检索、使用改写问题检索，或直接返回澄清问题
- 现有 `MilvusRetriever` 保持职责单一，只处理检索，不接入追问判定逻辑

**模块边界**

- `backend/rag/followup_resolver.py`
  - 定义 `FollowupResolver`
  - 定义结构化结果对象，例如 `FollowupResolution`
  - 封装提示词、LLM 调用、JSON 解析、规则补强和兜底逻辑
- `backend/rag/llm_client.py`
  - 扩展为支持按调用覆盖 `model_name`
  - 允许同一个 OpenAI-compatible client 同时服务主模型与快模型
- `backend/rag/pipeline.py`
  - 在 `retriever.retrieve()` 之前插入追问解析逻辑
  - 根据 resolution 结果决定检索路径或澄清路径
- `config.py`
  - 新增 `fast_model_name`
  - 新增 `followup_history_turns`
  - 新增 `followup_confidence_threshold`

**LLM 分工**

- 主模型：
  - 来源：`MODEL_NAME`
  - 作用：基于召回证据生成最终回答
  - 不负责追问判断和问题改写
- 快模型：
  - 来源：`FAST_MODEL_NAME`
  - 作用：追问识别、指代补全、歧义判断、澄清问题生成
  - 不负责最终答案生成
- 两者默认共用同一个 `BASE_URL` 和 `API_KEY`
- `LLMClient.answer_messages()` 增加可选参数 `model_name`
  - 未显式传值时沿用 `settings.model_name`
  - `FollowupResolver` 显式传 `settings.fast_model_name`

**前置判定数据流**

1. 前端将用户问题发到 `/api/projects/{project_name}/chat`
2. `ResearchRAGPipeline.answer_question()` 清洗 query 并获取 `conversation_id`
3. Pipeline 读取最近 `N` 轮历史消息
4. Pipeline 调用 `FollowupResolver.resolve()`
5. `FollowupResolver` 输出：
   - `original_query`
   - `resolved_query`
   - `is_followup`
   - `confidence`
   - `needs_clarification`
   - `clarification_question`
   - `reason`
6. Pipeline 按以下规则分流：
   - `is_followup = false`：使用原 query 检索
   - `is_followup = true` 且 `confidence >= threshold` 且 `needs_clarification = false`：使用 `resolved_query` 检索
   - `is_followup = true` 且低置信度或 `needs_clarification = true`：不检索，直接返回澄清问题
7. 若进入检索，后续保留现有召回与答案生成流程

**判定规则**

- 优先识别这类追问特征：
  - “那……呢”
  - “它/这个/那个”
  - “和另一篇比”
  - “上面提到的”
  - 时间、主体或指标省略，如“那 2025 年呢”
- 快模型只做有限任务：
  - 判断当前句子是否依赖历史上下文
  - 如果依赖，改写成一个可独立检索的问题
  - 如果存在多个合理解释对象，必须触发澄清
- 规则层只做轻量补强，不替代快模型：
  - 为明显追问信号增加“追问倾向”
  - 在中等置信度区间作为放行或转澄清的辅助条件

**阈值策略**

- `confidence >= 0.8` 且 `needs_clarification = false`：直接自动改写并检索
- `0.5 <= confidence < 0.8`：
  - 若规则层命中强追问信号，则允许自动改写并检索
  - 否则先返回澄清问题
- `confidence < 0.5`：直接返回澄清问题
- 若快模型输出不可解析、字段缺失或请求失败：
  - 记录日志
  - 兜底按“非追问”处理，不阻断主链路

**提示词要求**

- 快模型提示词必须要求返回固定 JSON，不允许自由发挥
- JSON 中必须包含：
  - `is_followup`
  - `resolved_query`
  - `confidence`
  - `needs_clarification`
  - `clarification_question`
  - `reason`
- 提示词必须明确：
  - 只能依据当前问题和提供的历史消息判断
  - 若可独立理解则判定为非追问
  - 若有两个及以上合理指代对象，必须要求澄清
  - `resolved_query` 必须是一个可直接送入检索的完整中文问题

**API 返回设计**

- 保持 `/chat` 现有响应兼容，但增加 `type` 和追问解析字段
- 正常回答时返回：
  - `type: "answer"`
  - `answer`
  - `sources`
  - `conversation_id`
  - `resolved_query`
- 澄清分支返回：
  - `type: "clarification"`
  - `answer`：直接放澄清问题，兼容旧前端
  - `sources: []`
  - `conversation_id`
  - `resolved_query: null`
  - `clarification`
    - `question`
    - `reason`

**会话持久化**

- 正常检索回答时，继续按现有方式写入 user/assistant 消息
- 澄清分支也要把 assistant 澄清问题写入会话
- 这样下一轮用户补充“我指的是华泰这篇”时，`FollowupResolver` 可以使用完整上下文

**错误处理**

- 快模型调用失败：记录日志，按“非追问”降级
- 快模型输出非 JSON：记录日志，按“非追问”降级
- `FAST_MODEL_NAME` 未配置：
  - 默认回退为 `MODEL_NAME`
  - 保证系统仍可运行
- 历史消息为空：直接按独立问题处理

**测试**

- 新增 `FollowupResolver` 单测：
  - 非追问问题原样放行
  - 高置信度追问返回改写问题
  - 多候选指代触发澄清
  - 快模型异常时回退为非追问
- 扩展 `tests/test_pipeline_conversations.py`
  - 普通问题使用原 query 检索
  - 追问问题使用 `resolved_query` 检索
  - 澄清分支不调用 retriever
  - 澄清消息会写入 conversation
- 扩展 `tests/test_llm_client.py`
  - 支持按调用覆盖 `model_name`
- 扩展 API 测试
  - `type="answer"` 返回 `resolved_query`
  - `type="clarification"` 返回 `clarification.question`

**验收标准**

- 用户输入明显追问时，系统可以在最近 `N` 轮上下文内补全为独立问题再检索
- 用户输入存在多义指代时，系统优先澄清而不是误检索
- 快模型异常不会导致主问答链路不可用
- 现有普通单轮问答行为不回归

**本期不做**

- 更广义的多意图路由，如项目操作、文档管理、元信息查询
- 基于检索结果再做二次指代消解
- 多模型多 provider 独立配置
