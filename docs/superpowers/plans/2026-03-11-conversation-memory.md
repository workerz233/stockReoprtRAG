# Conversation Memory Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目问答增加可持久化的会话记忆，并支持历史对话删除与下次打开可见。

**Architecture:** 新增项目级会话存储层，聊天接口显式携带 `conversation_id`。RAG 检索仍按当前问题执行，LLM 输入改为 `system + 最近历史消息 + 当前轮带证据的问题`，会话消息按 JSON 持久化到项目目录。前端增加会话列表与切换/删除能力。

**Tech Stack:** FastAPI, Pydantic, 本地 JSON 文件持久化, OpenAI-compatible chat completions, 原生前端 JS

---

## Chunk 1: 会话存储层与后端接口

### Task 1: 定义会话存储回归测试

**Files:**
- Create: `tests/test_conversation_manager.py`
- Create: `backend/conversation_manager.py`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run test to verify it passes**

### Task 2: 接入 FastAPI 会话接口

**Files:**
- Modify: `app.py`
- Modify: `backend/project_manager.py`
- Test: `tests/test_api_conversations.py`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run test to verify it passes**

## Chunk 2: LLM 多消息上下文与聊天持久化

### Task 3: 扩展 LLM client 为 messages 模式

**Files:**
- Modify: `backend/rag/llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run test to verify it passes**

### Task 4: 在 RAG pipeline 中拼接历史并保存消息

**Files:**
- Modify: `backend/rag/pipeline.py`
- Modify: `app.py`
- Test: `tests/test_pipeline_conversations.py`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run test to verify it passes**

## Chunk 3: 前端会话管理

### Task 5: 接入会话列表、切换与删除

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

- [ ] **Step 1: 先补最小 UI 结构**
- [ ] **Step 2: 接入会话 API 与状态管理**
- [ ] **Step 3: 串联聊天请求中的 `conversation_id`**
- [ ] **Step 4: 手工验证切换、持久化与删除流程**
