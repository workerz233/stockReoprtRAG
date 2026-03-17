# Followup Resolution Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pre-retrieval followup detection, pronoun resolution, and clarification routing to project chat while using `FAST_MODEL_NAME` as a dedicated fast model.

**Architecture:** Keep retrieval unchanged and insert a new `FollowupResolver` before `MilvusRetriever.retrieve()`. Extend the existing `LLMClient` to support per-call model overrides so the resolver can use `FAST_MODEL_NAME` while the answering flow keeps using `MODEL_NAME`.

**Tech Stack:** FastAPI, Python 3, unittest, OpenAI-compatible chat completions, local conversation persistence

---

## Chunk 1: Config And LLM Plumbing

### Task 1: Add failing config coverage for fast-model settings

**Files:**
- Modify: `tests/test_llm_client.py`
- Modify: `config.py`

- [ ] **Step 1: Write the failing test**

```python
settings = self.module.Settings(
    base_url="http://localhost:8001/v1",
    model_name="main-model",
    fast_model_name="fast-model",
    api_key="token",
)
client = self.module.LLMClient(settings=settings)
client.answer_messages([{"role": "user", "content": "test"}], model_name="fast-model")
assert client.client.chat.completions.last_kwargs["model"] == "fast-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_client.py -q`
Expected: FAIL because `Settings` and `answer_messages()` do not yet support `fast_model_name` / `model_name` override.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class Settings:
    base_url: str
    model_name: str
    fast_model_name: str | None = None

def answer_messages(..., model_name: str | None = None) -> str:
    selected_model = model_name or self.settings.model_name
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_client.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_llm_client.py config.py backend/rag/llm_client.py
git commit -m "feat: support fast model overrides"
```

### Task 2: Add streaming parity for model override support

**Files:**
- Modify: `tests/test_llm_client.py`
- Modify: `backend/rag/llm_client.py`

- [ ] **Step 1: Write the failing test**

```python
chunks = list(
    client.stream_answer_messages(
        [{"role": "user", "content": "流式问题"}],
        model_name="fast-model",
    )
)
assert client.client.chat.completions.last_kwargs["model"] == "fast-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_client.py -q`
Expected: FAIL because `stream_answer_messages()` does not yet accept `model_name`.

- [ ] **Step 3: Write minimal implementation**

```python
def stream_answer_messages(..., model_name: str | None = None):
    selected_model = model_name or self.settings.model_name
    response = self.client.chat.completions.create(
        model=selected_model,
        ...
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_client.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_llm_client.py backend/rag/llm_client.py
git commit -m "feat: add streaming model override support"
```

## Chunk 2: Followup Resolver

### Task 3: Create resolver tests for pass-through, rewrite, and clarification

**Files:**
- Create: `tests/test_followup_resolver.py`
- Create: `backend/rag/followup_resolver.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_independent_query_passes_through():
    resolver = FollowupResolver(...)
    result = resolver.resolve("存储行业景气度怎么看", history_messages=[])
    assert result.is_followup is False
    assert result.resolved_query == "存储行业景气度怎么看"

def test_followup_query_is_rewritten():
    fake_llm.response = {
        "is_followup": True,
        "resolved_query": "华泰证券对存储行业2025年景气度的判断是什么？",
        "confidence": 0.91,
        "needs_clarification": False,
        "clarification_question": "",
        "reason": "..."
    }
    result = resolver.resolve("那2025年呢", history_messages=[...])
    assert result.resolved_query == "华泰证券对存储行业2025年景气度的判断是什么？"

def test_ambiguous_reference_requests_clarification():
    fake_llm.response = {
        "is_followup": True,
        "resolved_query": "",
        "confidence": 0.62,
        "needs_clarification": True,
        "clarification_question": "你指的是华泰证券还是华西证券这篇报告？",
        "reason": "..."
    }
    result = resolver.resolve("它的毛利率呢", history_messages=[...])
    assert result.needs_clarification is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_followup_resolver.py -q`
Expected: FAIL because resolver module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class FollowupResolution:
    original_query: str
    resolved_query: str | None
    is_followup: bool
    confidence: float
    needs_clarification: bool
    clarification_question: str | None
    reason: str

class FollowupResolver:
    def resolve(self, query: str, history_messages: list[dict[str, str]]) -> FollowupResolution:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_followup_resolver.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_followup_resolver.py backend/rag/followup_resolver.py
git commit -m "feat: add followup resolver"
```

### Task 4: Add resolver fallback and threshold behavior

**Files:**
- Modify: `tests/test_followup_resolver.py`
- Modify: `backend/rag/followup_resolver.py`
- Modify: `config.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_invalid_json_falls_back_to_non_followup():
    fake_llm.raw_response = "not-json"
    result = resolver.resolve("那它呢", history_messages=[...])
    assert result.is_followup is False
    assert result.resolved_query == "那它呢"

def test_mid_confidence_requires_rule_hit_to_auto_resolve():
    fake_llm.response = {... "confidence": 0.65, "needs_clarification": False}
    result = resolver.resolve("那2025年呢", history_messages=[...])
    assert result.is_followup is True
    assert result.resolved_query is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_followup_resolver.py -q`
Expected: FAIL because fallback and threshold logic is not complete yet.

- [ ] **Step 3: Write minimal implementation**

```python
if parsing_failed:
    return FollowupResolution(..., is_followup=False, resolved_query=query)

if 0.5 <= confidence < threshold and not self._has_strong_followup_signal(query):
    return FollowupResolution(..., needs_clarification=True, clarification_question=...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_followup_resolver.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_followup_resolver.py backend/rag/followup_resolver.py config.py
git commit -m "feat: add resolver fallback thresholds"
```

## Chunk 3: Pipeline Integration

### Task 5: Add pipeline tests for rewritten-query retrieval and clarification routing

**Files:**
- Modify: `tests/test_pipeline_conversations.py`
- Modify: `backend/rag/pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_answer_question_uses_resolved_query_for_retrieval():
    pipeline.followup_resolver = FakeResolver.resolved("华泰证券对存储行业2025年景气度的判断是什么？")
    pipeline.answer_question("demo", "那2025年呢", conversation_id="conv-1")
    assert pipeline.retriever.last_query == "华泰证券对存储行业2025年景气度的判断是什么？"

def test_answer_question_returns_clarification_without_retrieval():
    pipeline.followup_resolver = FakeResolver.clarification("你指的是华泰证券还是华西证券这篇报告？")
    result = pipeline.answer_question("demo", "它的毛利率呢", conversation_id="conv-1")
    assert result["type"] == "clarification"
    assert result["sources"] == []
    assert pipeline.retriever.last_query is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: FAIL because pipeline has no followup resolver integration or clarification branch.

- [ ] **Step 3: Write minimal implementation**

```python
resolution = self.followup_resolver.resolve(query, history_messages=history_messages)
if resolution.needs_clarification:
    return {
        "type": "clarification",
        "answer": resolution.clarification_question,
        "sources": [],
        "resolved_query": None,
    }
retrieval_query = resolution.resolved_query or query
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_conversations.py backend/rag/pipeline.py
git commit -m "feat: route chat through followup resolver"
```

### Task 6: Cover streaming chat behavior for clarification responses

**Files:**
- Modify: `tests/test_pipeline_conversations.py`
- Modify: `backend/rag/pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
def test_stream_answer_question_emits_clarification_without_sources_event():
    pipeline.followup_resolver = FakeResolver.clarification("你指的是哪篇报告？")
    events = list(pipeline.stream_answer_question("demo", "它的毛利率呢", conversation_id="conv-1"))
    assert [event["type"] for event in events] == ["start", "delta", "done"]
    assert events[-1]["answer"] == "你指的是哪篇报告？"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: FAIL because streaming path always assumes retrieval + sources flow.

- [ ] **Step 3: Write minimal implementation**

```python
if resolution.needs_clarification:
    answer = resolution.clarification_question
    self._persist_conversation_turn(...)
    yield {"type": "delta", "delta": answer}
    yield {"type": "done", "conversation_id": conversation_id, "answer": answer}
    return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_conversations.py backend/rag/pipeline.py
git commit -m "feat: support clarification in streaming chat"
```

## Chunk 4: API Contract And Docs

### Task 7: Add API tests for answer and clarification payloads

**Files:**
- Modify: `tests/test_api_conversations.py`
- Modify: `app.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_chat_endpoint_returns_answer_payload():
    self.app_module.pipeline.answer_question = lambda *args, **kwargs: {
        "type": "answer",
        "answer": "第一段",
        "sources": [],
        "resolved_query": "完整问题",
        "conversation_id": "conv-1",
    }
    response = self.client.post("/api/projects/demo/chat", json={"query": "那2025年呢"})
    assert response.json()["type"] == "answer"

def test_chat_endpoint_returns_clarification_payload():
    self.app_module.pipeline.answer_question = lambda *args, **kwargs: {
        "type": "clarification",
        "answer": "你指的是华泰证券还是华西证券这篇报告？",
        "sources": [],
        "resolved_query": None,
        "clarification": {"question": "...", "reason": "..."},
        "conversation_id": "conv-1",
    }
    response = self.client.post("/api/projects/demo/chat", json={"query": "它的毛利率呢"})
    assert response.json()["type"] == "clarification"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_conversations.py -q`
Expected: FAIL because the fake pipeline and endpoint tests do not yet cover `answer_question()` payloads.

- [ ] **Step 3: Write minimal implementation**

```python
class FakePipeline:
    def answer_question(...):
        return {...}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_conversations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_conversations.py app.py
git commit -m "test: cover chat followup payloads"
```

### Task 8: Run focused verification and update docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the failing-or-missing documentation expectation**

Document:
- `FAST_MODEL_NAME`
- Followup resolution behavior
- Clarification response shape

- [ ] **Step 2: Update README minimally**

```markdown
- `MODEL_NAME`: final answer model
- `FAST_MODEL_NAME`: followup resolution model
```

- [ ] **Step 3: Run focused verification**

Run: `python -m pytest tests/test_llm_client.py tests/test_followup_resolver.py tests/test_pipeline_conversations.py tests/test_api_conversations.py -q`
Expected: PASS

- [ ] **Step 4: Run one broader smoke check**

Run: `python -m pytest -q`
Expected: PASS, or a clearly explained pre-existing unrelated failure.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_llm_client.py tests/test_followup_resolver.py tests/test_pipeline_conversations.py tests/test_api_conversations.py config.py backend/rag/llm_client.py backend/rag/followup_resolver.py backend/rag/pipeline.py app.py
git commit -m "feat: add followup query resolution"
```
