# SSE Chat Streaming Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace synchronous `/chat` responses with POST-based SSE streaming and include retrieval sources in the final event.

**Architecture:** Extend the existing RAG pipeline with a streaming answer path that retrieves first, streams LLM deltas second, then persists the final assistant message and emits one terminal SSE event containing the structured sources. Keep the route path and request body unchanged so frontend state management only changes at the response-consumption layer.

**Tech Stack:** FastAPI, Uvicorn, Python 3, unittest, OpenAI-compatible chat completions, vanilla browser `fetch` streams

---

## Chunk 1: Backend Streaming Primitives

### Task 1: Add failing LLM client tests for streaming output

**Files:**
- Modify: `tests/test_llm_client.py`
- Modify: `backend/rag/llm_client.py`

- [ ] **Step 1: Write the failing test**

```python
chunks = list(client.stream_answer_messages([{"role": "user", "content": "流式问题"}]))
assert chunks == ["第一段", "第二段"]
assert client.client.chat.completions.last_kwargs["stream"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_client.py -q`
Expected: FAIL because `stream_answer_messages()` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def stream_answer_messages(...):
    response = self.client.chat.completions.create(..., stream=True)
    for chunk in response:
        yield delta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_client.py -q`
Expected: PASS

### Task 2: Add failing pipeline tests for streaming answer assembly

**Files:**
- Modify: `tests/test_pipeline_conversations.py`
- Modify: `backend/rag/pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
events = list(pipeline.stream_answer_question("demo", "这一轮问题", conversation_id="conv-1"))
assert events[0]["type"] == "start"
assert events[1]["type"] == "token"
assert events[-1]["type"] == "done"
assert events[-1]["sources"][0]["report_name"] == "demo.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: FAIL because the streaming pipeline API does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
async def stream_answer_question(...):
    yield {"type": "start", ...}
    for delta in self.llm_client.stream_answer_messages(...):
        yield {"type": "token", "delta": delta}
    yield {"type": "done", "answer": answer, "sources": sources, ...}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: PASS

## Chunk 2: SSE API

### Task 3: Add failing API tests for SSE framing

**Files:**
- Modify: `tests/test_api_conversations.py`
- Modify: `app.py`

- [ ] **Step 1: Write the failing test**

```python
response = self.client.post("/api/projects/demo/chat", json={"query": "问题"})
assert response.status_code == 200
assert response.headers["content-type"].startswith("text/event-stream")
assert "event: done" in response.text
assert '"sources"' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_conversations.py -q`
Expected: FAIL because the route still returns JSON.

- [ ] **Step 3: Write minimal implementation**

```python
@app.post("/api/projects/{project_name}/chat")
async def chat(...):
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_conversations.py -q`
Expected: PASS

## Chunk 3: Frontend Consumption

### Task 4: Update chat UI to parse SSE from `fetch`

**Files:**
- Modify: `frontend/app.js`

- [ ] **Step 1: Replace JSON chat submission with stream parsing**

```javascript
const response = await fetch(url, options);
const reader = response.body.getReader();
const decoder = new TextDecoder();
```

- [ ] **Step 2: Parse SSE frames and update the assistant placeholder**

```javascript
if (eventName === "token") {
  assistantText += payload.delta;
  updateMessage(...);
}
```

- [ ] **Step 3: Attach sources from the final `done` event**

```javascript
if (eventName === "done") {
  updateMessage("assistant", payload.answer, payload.sources);
}
```

- [ ] **Step 4: Manually verify in browser or via targeted tests if available**

Run: project startup command and send one chat request
Expected: answer appears incrementally and sources appear only at the end

## Chunk 4: Verification

### Task 5: Run targeted regression checks

**Files:**
- Modify: `tests/test_llm_client.py`
- Modify: `tests/test_pipeline_conversations.py`
- Modify: `tests/test_api_conversations.py`

- [ ] **Step 1: Run backend unit tests**

Run: `python -m pytest tests/test_llm_client.py tests/test_pipeline_conversations.py tests/test_api_conversations.py -q`
Expected: PASS

- [ ] **Step 2: Run one end-to-end smoke check if environment permits**

Run: `bash start.sh`
Expected: backend serves SSE and frontend renders incremental chat output

- [ ] **Step 3: Summarize remaining risks**

Confirm:
- reverse proxy does not buffer SSE
- frontend parser handles split frames
- final event always carries `sources`
