# Chat Markdown And Streaming Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add assistant-side Markdown rendering and LLM streaming chat responses without breaking existing conversation persistence or the blocking chat API.

**Architecture:** Keep the blocking `/chat` endpoint intact and add a new NDJSON streaming endpoint that reuses the same retrieval and conversation logic. Extend the frontend to consume streaming events, update a placeholder assistant bubble incrementally, and sanitize-render assistant Markdown while leaving user messages as plain text.

**Tech Stack:** FastAPI, OpenAI-compatible Python SDK, vanilla JavaScript, browser `fetch()` streams, vendored Markdown parser and sanitizer, unittest/pytest-style existing test suite.

---

## Chunk 1: Backend Streaming Primitives

### Task 1: Add failing LLM client streaming tests

**Files:**
- Modify: `tests/test_llm_client.py`
- Modify: `backend/rag/llm_client.py`

- [ ] **Step 1: Write the failing test**

Add tests that construct a fake streamed completion sequence and assert `LLMClient.stream_answer_messages(...)` yields only non-empty text deltas.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_client.py -q`
Expected: FAIL because `stream_answer_messages` does not exist.

- [ ] **Step 3: Write minimal implementation**

Add a streaming method to `LLMClient` that calls `chat.completions.create(..., stream=True)` and yields delta content strings.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_client.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_llm_client.py backend/rag/llm_client.py
git commit -m "feat: add llm streaming client support"
```

### Task 2: Add failing pipeline streaming tests

**Files:**
- Modify: `tests/test_pipeline_conversations.py`
- Modify: `backend/rag/pipeline.py`

- [ ] **Step 1: Write the failing test**

Add tests that stream an answer through the pipeline, assert event ordering, and verify the conversation file is updated only after completion.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_conversations.py -q`
Expected: FAIL because the pipeline has no streaming interface.

- [ ] **Step 3: Write minimal implementation**

Refactor shared retrieval/prompt setup into helpers and add a generator method like `stream_answer_question(...)` that yields event dictionaries and persists the final turn only on success.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline_conversations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_conversations.py backend/rag/pipeline.py
git commit -m "feat: stream rag pipeline responses"
```

## Chunk 2: API Streaming Endpoint

### Task 3: Add failing API streaming tests

**Files:**
- Modify: `tests/test_api_conversations.py`
- Modify: `app.py`

- [ ] **Step 1: Write the failing test**

Add API tests that call `POST /api/projects/demo/chat/stream`, consume the returned body, and assert the NDJSON event sequence includes `start` and `done`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_conversations.py -q`
Expected: FAIL with 404 or missing route.

- [ ] **Step 3: Write minimal implementation**

Add the FastAPI route and wrap the pipeline event generator in a `StreamingResponse` that serializes one JSON object per line.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_conversations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_conversations.py app.py
git commit -m "feat: add streaming chat api"
```

## Chunk 3: Frontend Markdown Rendering And Stream Consumption

### Task 4: Prepare frontend rendering tests-by-structure

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`

- [ ] **Step 1: Identify the rendering seams**

Extract helper functions for user bubble rendering, assistant Markdown rendering, placeholder creation, and NDJSON stream parsing so behavior is localized and manually verifiable.

- [ ] **Step 2: Add the required assets**

Vendor or include lightweight Markdown parsing and sanitization bundles in the frontend and load them from `index.html`.

- [ ] **Step 3: Implement minimal stream-aware UI**

Update message sending to call `/chat/stream`, append the user message immediately, incrementally update an assistant placeholder from `delta` events, and attach sources on completion.

- [ ] **Step 4: Add Markdown-specific styling**

Style assistant bubble content for paragraphs, headings, lists, code, blockquotes, links, and tables without affecting user bubbles.

- [ ] **Step 5: Manually verify**

Run the app locally, send a question that yields a multi-paragraph answer, and confirm Markdown formatting and incremental updates appear correctly.

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css
git commit -m "feat: render markdown in streamed chat responses"
```

## Chunk 4: End-To-End Verification

### Task 5: Run targeted verification

**Files:**
- Modify: `tests/test_api_conversations.py`
- Modify: `tests/test_pipeline_conversations.py`
- Modify: `tests/test_llm_client.py`

- [ ] **Step 1: Run backend tests**

Run: `pytest tests/test_llm_client.py tests/test_pipeline_conversations.py tests/test_api_conversations.py -q`
Expected: PASS

- [ ] **Step 2: Run broader regression tests if cheap**

Run: `pytest tests/test_conversation_manager.py -q`
Expected: PASS

- [ ] **Step 3: Smoke test the browser flow**

Run the app and confirm:
- user messages still render as plain text
- assistant messages render Markdown
- streamed answer grows progressively
- completed conversation reloads correctly

- [ ] **Step 4: Commit final integration changes if needed**

```bash
git add tests/test_api_conversations.py tests/test_pipeline_conversations.py tests/test_llm_client.py
git commit -m "test: cover streaming chat flow"
```
