# Semantic Intent Routing Design

**Date:** 2026-03-17

## Goal

将当前基于 `followup_resolver` 的多轮意图识别机制重构为统一的 `semantic-router` 语义路由入口，并将查询改写与澄清追问拆分为独立执行器。重构后，所有聊天查询先经过语义路由，再按路由类型进入闲聊、历史问答、历史改写后检索、独立检索或直接追问链路。

## Current State

当前实现中，多轮机制分散在 [`backend/rag/followup_resolver.py`](/Users/zzz/RschProjects/stockReportRAG/backend/rag/followup_resolver.py) 与 [`backend/rag/pipeline.py`](/Users/zzz/RschProjects/stockReportRAG/backend/rag/pipeline.py)：

- `pipeline.py` 先用正则判断是否属于 `history-only` 提问
- 其余问题交给 `FollowupResolver`
- `FollowupResolver` 使用快模型同时承担“是否追问”“是否需要澄清”“查询改写”三个职责
- 追问信号与阈值部分仍依赖硬编码规则

这个结构的问题是职责耦合严重，意图分类不可扩展，也不适合继续增加闲聊等新路由。

## Target Architecture

重构后的入口链路为：

`query + history -> semantic-router -> route decision -> route executor -> final response`

新增统一路由模块，所有聊天请求都先经过语义路由，路由器只判断意图类型，不负责生成最终答复内容。

### Route Types

系统统一支持以下 5 类路由：

- `chitchat`
  闲聊或非检索型对话，直接交给主 LLM，不走检索。
- `history_qa`
  只依赖当前会话历史即可回答的问题，不走检索。
- `history_rewrite_retrieval`
  依赖上下文、需要先改写为独立查询后再检索的问题。
- `direct_retrieval`
  当前问题本身已足够独立，直接检索。
- `clarification`
  信息不足或指代不清，直接返回追问，不检索。

## Module Boundaries

### 1. `backend/rag/intent_router.py`

职责：

- 加载外部 route 配置
- 初始化 `semantic-router`
- 将历史消息格式化为路由输入
- 输出统一的路由结果对象

建议输出对象字段：

- `route_name`
- `confidence`
- `reason`
- `query`
- `history_messages`

该模块只负责分类，不做查询改写，不生成追问文案。

### 2. `backend/rag/query_rewriter.py`

职责：

- 仅服务 `history_rewrite_retrieval`
- 使用 `.env` 中现有 `FAST_MODEL_NAME`
- 输入 `query + history_messages`
- 输出 standalone retrieval query

改写失败时回退到原始 query，不中断主流程。

### 3. `backend/rag/clarification_generator.py`

职责：

- 仅服务 `clarification`
- 使用 `.env` 中现有 `FAST_MODEL_NAME`
- 基于 `query + history_messages` 生成简短追问句

生成失败时回退固定兜底文案：

`我需要确认一下你指的是上一轮中的哪个报告、公司或指标？`

### 4. `backend/rag/pipeline.py`

职责：

- 保持唯一编排层角色
- 调用 `intent_router` 获取路由结果
- 按 route 分发到不同执行链路
- 维持当前 API 返回结构，避免前端与接口大范围改动

## Route Configuration

`semantic-router` 的 route utterances 不内置到 Python 代码，改为独立配置文件维护。建议新增：

- [`config/semantic_routes.json`](/Users/zzz/RschProjects/stockReportRAG/config/semantic_routes.json)

每个 route 配置项至少包含：

- `name`
- `description`
- `utterances`

这样做的原因：

- 调整路由样本时不需要改 Python 逻辑
- 评测和版本对比更容易
- 路由定义与执行器边界清晰

如果配置文件缺失或格式非法，系统降级到保守模式，不中断聊天主流程。

## Execution Flow

### `chitchat`

- 路由命中 `chitchat`
- 直接调用主 LLM
- 不触发检索
- `resolved_query` 返回 `None`

### `history_qa`

- 路由命中 `history_qa`
- 直接调用历史回答器
- 不触发检索
- `resolved_query` 返回 `None`

### `history_rewrite_retrieval`

- 路由命中 `history_rewrite_retrieval`
- 调用 `query_rewriter` 使用 `FAST_MODEL_NAME` 改写查询
- 用改写后的 query 检索
- 由主 LLM 基于检索证据生成回答
- `resolved_query` 返回改写后的 query

### `direct_retrieval`

- 路由命中 `direct_retrieval`
- 直接使用原始 query 检索
- 由主 LLM 基于检索证据生成回答
- `resolved_query` 返回原始 query

### `clarification`

- 路由命中 `clarification`
- 调用 `clarification_generator` 生成追问句
- 直接返回追问，不触发检索
- 返回结构继续包含 `clarification.question` 与 `clarification.reason`

## Failure Handling

### Router Failure

当 `semantic-router` 初始化失败、配置缺失或推理结果不可用时，进入保守降级逻辑：

- 明显历史总结类问题 -> `history_qa`
- 明显短指代且存在历史 -> `clarification`
- 其余问题 -> `direct_retrieval`

### Rewriter Failure

- 回退为原 query
- 记录日志
- 不中断主问答流程

### Clarification Generation Failure

- 返回固定兜底追问文案
- 保持 `type=clarification`

## Compatibility Requirements

本次重构不改变聊天接口的核心响应结构：

- 正常回答仍返回 `type=answer`
- 澄清仍返回 `type=clarification`
- SSE 仍保留 `start` / token 或 delta / `done` 事件结构
- 前端继续读取 `answer`、`sources`、`resolved_query`、`clarification`

## Testing Strategy

测试覆盖分四层：

1. 路由器单测
   验证 5 类路由、配置加载、降级逻辑、空历史与短指代边界。
2. 查询改写/追问生成单测
   验证 `FAST_MODEL_NAME` 被正确使用，失败时存在回退。
3. Pipeline 单测
   验证 5 条主链路及其 `resolved_query` / `sources` / `clarification` 行为。
4. API 与流式回归测试
   验证 `/api/projects/{project}/chat` 及 SSE 行为兼容。

## Non-Goals

- 不调整检索、向量库或索引逻辑
- 不改动前端交互协议
- 不在本次重构中引入动态在线 route 管理界面
