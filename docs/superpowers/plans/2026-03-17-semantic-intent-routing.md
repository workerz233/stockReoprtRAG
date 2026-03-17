# Semantic Intent Routing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current followup-resolution mechanism with a `semantic-router`-driven intent layer that routes chat queries into chitchat, history QA, history rewrite + retrieval, direct retrieval, or clarification, while using `FAST_MODEL_NAME` for query rewriting and clarification generation.

**Architecture:** Add a new intent router that loads route definitions from external JSON config and returns a single route decision for each query. Keep execution concerns separate by adding a query rewriter and clarification generator, then update the pipeline to dispatch on the selected route without changing the public chat response shape.

**Tech Stack:** FastAPI, Python 3, unittest, OpenAI-compatible chat completions, semantic-router, local JSON config, local conversation persistence

---

## Chunk 1: Dependency And Route Configuration

### Task 1: Add route config fixture and failing loader tests

**Files:**
- Create: `config/semantic_routes.json`
- Create: `tests/test_intent_router.py`

- [ ] **Step 1: Write the failing tests**

```python
router = IntentRouter(llm_client=None, settings=self.settings)
routes = router._load_route_definitions()
assert {route.name for route in routes} == {
    "chitchat",
    "history_qa",
    "history_rewrite_retrieval",
    "direct_retrieval",
    "clarification",
}
assert all(route.utterances for route in routes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_intent_router.py -q`
Expected: FAIL because the route config file and loader do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
[
  {"name": "chitchat", "description": "...", "utterances": ["你好", "你是谁"]},
  ...
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_intent_router.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config/semantic_routes.json tests/test_intent_router.py backend/rag/intent_router.py
git commit -m "feat: add semantic route config loader"
```

### Task 2: Add dependency coverage for `semantic-router`

**Files:**
- Modify: `requirements.txt`
- Modify: `tests/test_intent_router.py`

- [ ] **Step 1: Write the failing test**

```python
router = IntentRouter(llm_client=None, settings=self.settings)
assert router.router is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_intent_router.py -q`
Expected: FAIL because the `semantic-router` dependency and router construction are not wired yet.

- [ ] **Step 3: Write minimal implementation**

```python
# requirements.txt
semantic-router>=0.1.0
```

```python
self.router = RouteLayer(encoder=..., routes=routes)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_intent_router.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/test_intent_router.py backend/rag/intent_router.py
git commit -m "feat: wire semantic-router dependency"
```

## Chunk 2: Router, Rewriter, And Clarification Executors

### Task 3: Create failing intent-router tests for route decisions and fallback

**Files:**
- Modify: `tests/test_intent_router.py`
- Create: `backend/rag/intent_router.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_route_history_summary_to_history_qa():
    decision = router.route("总结一下上文", history_messages=[...])
    assert decision.route_name == "history_qa"

def test_route_short_pronoun_to_clarification_when_history_is_insufficient():
    decision = router.route("它怎么样", history_messages=[...])
    assert decision.route_name == "clarification"

def test_router_falls_back_to_direct_retrieval_when_config_is_unavailable():
    router = IntentRouter(..., route_config_path=missing_path)
    decision = router.route("宁德时代2025年盈利预测是多少", history_messages=[])
    assert decision.route_name == "direct_retrieval"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_intent_router.py -q`
Expected: FAIL because `IntentRouter.route()` and fallback logic do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class RouteDecision:
    route_name: str
    confidence: float
    reason: str
    query: str
    history_messages: list[dict[str, str]]

def route(self, query: str, history_messages: list[dict[str, str]]) -> RouteDecision:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_intent_router.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_intent_router.py backend/rag/intent_router.py
git commit -m "feat: add semantic intent router"
```

### Task 4: Create failing query rewriter tests with `FAST_MODEL_NAME`

**Files:**
- Create: `tests/test_query_rewriter.py`
- Create: `backend/rag/query_rewriter.py`

- [ ] **Step 1: Write the failing tests**

```python
rewriter = QueryRewriter(llm_client=fake_llm, settings=self.settings)
rewritten = rewriter.rewrite("那2025年呢", history_messages=[...])
assert rewritten == "华泰证券对存储行业2025年景气度的判断是什么？"
assert fake_llm.last_model_name == "fast-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_query_rewriter.py -q`
Expected: FAIL because the rewriter module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
payload = self.llm_client.answer_messages(..., model_name=self.settings.fast_model_name)
return payload.strip() or query
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_query_rewriter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_query_rewriter.py backend/rag/query_rewriter.py
git commit -m "feat: add query rewriter"
```

### Task 5: Create failing clarification generator tests with fallback

**Files:**
- Create: `tests/test_clarification_generator.py`
- Create: `backend/rag/clarification_generator.py`

- [ ] **Step 1: Write the failing tests**

```python
generator = ClarificationGenerator(llm_client=fake_llm, settings=self.settings)
question = generator.generate("它怎么样", history_messages=[...])
assert question == "你指的是上一轮中的哪家公司或哪篇报告？"
assert fake_llm.last_model_name == "fast-model"
```

```python
fake_llm.response = ""
question = generator.generate("它怎么样", history_messages=[...])
assert question == "我需要确认一下你指的是上一轮中的哪个报告、公司或指标？"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_clarification_generator.py -q`
Expected: FAIL because the clarification generator does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
payload = self.llm_client.answer_messages(..., model_name=self.settings.fast_model_name)
return payload.strip() or DEFAULT_CLARIFICATION_QUESTION
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_clarification_generator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_clarification_generator.py backend/rag/clarification_generator.py
git commit -m "feat: add clarification generator"
```

## Chunk 3: Pipeline Integration

### Task 6: Add failing pipeline tests for the five route paths

**Files:**
- Modify: `tests/test_pipeline_conversations.py`
- Modify: `backend/rag/pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_chitchat_route_skips_retrieval_and_uses_llm():
    pipeline.intent_router = FakeIntentRouter("chitchat")
    result = pipeline.answer_question("demo", "你好", conversation_id="conv-1")
    assert result["type"] == "answer"
    assert result["resolved_query"] is None
    assert pipeline.retriever.last_query is None

def test_history_rewrite_route_uses_rewritten_query_for_retrieval():
    pipeline.intent_router = FakeIntentRouter("history_rewrite_retrieval")
    pipeline.query_rewriter = FakeRewriter("华泰证券对存储行业2025年景气度的判断是什么？")
    result = pipeline.answer_question("demo", "那2025年呢", conversation_id="conv-1")
    assert result["resolved_query"] == "华泰证券对存储行业2025年景气度的判断是什么？"
    assert pipeline.retriever.last_query == "华泰证券对存储行业2025年景气度的判断是什么？"

def test_clarification_route_returns_direct_question_without_retrieval():
    pipeline.intent_router = FakeIntentRouter("clarification")
    pipeline.clarification_generator = FakeClarificationGenerator("你指的是哪篇报告？")
    result = pipeline.answer_question("demo", "它怎么样", conversation_id="conv-1")
    assert result["type"] == "clarification"
    assert result["clarification"]["question"] == "你指的是哪篇报告？"
    assert pipeline.retriever.last_query is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: FAIL because `pipeline.py` still depends on `FollowupResolver`.

- [ ] **Step 3: Write minimal implementation**

```python
decision = self.intent_router.route(query=query, history_messages=history_messages)
if decision.route_name == "chitchat":
    ...
elif decision.route_name == "history_qa":
    ...
elif decision.route_name == "history_rewrite_retrieval":
    retrieval_query = self.query_rewriter.rewrite(...)
elif decision.route_name == "direct_retrieval":
    retrieval_query = query
else:
    question = self.clarification_generator.generate(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_conversations.py backend/rag/pipeline.py backend/rag/intent_router.py backend/rag/query_rewriter.py backend/rag/clarification_generator.py
git commit -m "feat: route pipeline through semantic intent router"
```

### Task 7: Add failing SSE coverage for chitchat and clarification routing

**Files:**
- Modify: `tests/test_pipeline_conversations.py`
- Modify: `backend/rag/pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_stream_answer_question_skips_retrieval_for_chitchat():
    pipeline.intent_router = FakeIntentRouter("chitchat")
    events = collect_events(...)
    assert events[-1]["resolved_query"] is None
    assert pipeline.retriever.last_query is None

def test_stream_answer_question_returns_clarification_done_event():
    pipeline.intent_router = FakeIntentRouter("clarification")
    pipeline.clarification_generator = FakeClarificationGenerator("你指的是哪篇报告？")
    events = collect_events(...)
    assert events[-1]["type"] == "done"
    assert events[-1]["clarification"]["question"] == "你指的是哪篇报告？"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: FAIL because streaming still follows the old followup resolver branch.

- [ ] **Step 3: Write minimal implementation**

```python
if decision.route_name == "clarification":
    yield {"type": "delta", "delta": answer, ...}
    yield {"type": "done", "clarification": {...}, "resolved_query": None, ...}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pipeline_conversations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_conversations.py backend/rag/pipeline.py
git commit -m "feat: add streaming semantic route handling"
```

## Chunk 4: API And Documentation Regression

### Task 8: Add failing API tests for chitchat, rewritten retrieval, and clarification payloads

**Files:**
- Modify: `tests/test_api_conversations.py`
- Modify: `app.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_chat_endpoint_returns_answer_payload_for_chitchat():
    response = self.client.post("/api/projects/demo/chat", json={"query": "你好"})
    assert response.json()["type"] == "answer"
    assert response.json()["resolved_query"] is None

def test_chat_endpoint_returns_rewritten_query_payload():
    response = self.client.post("/api/projects/demo/chat", json={"query": "那2025年呢"})
    assert response.json()["resolved_query"] == "华泰证券对存储行业2025年景气度的判断是什么？"

def test_chat_endpoint_returns_clarification_payload():
    response = self.client.post("/api/projects/demo/chat", json={"query": "它怎么样"})
    assert response.json()["type"] == "clarification"
    assert response.json()["clarification"]["question"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_conversations.py -q`
Expected: FAIL because the endpoint mocks and response assumptions still target the old followup resolver.

- [ ] **Step 3: Write minimal implementation**

```python
# Update endpoint integration only as needed to preserve existing response shape.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_conversations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_conversations.py app.py
git commit -m "test: cover semantic route chat payloads"
```

### Task 9: Update README and remove followup-resolver references

**Files:**
- Modify: `README.md`
- Modify: `backend/rag/pipeline.py`
- Delete: `backend/rag/followup_resolver.py`

- [ ] **Step 1: Write the failing doc expectation**

```python
assert "semantic-router" in Path("README.md").read_text(encoding="utf-8")
assert "followup_resolver" not in Path("backend/rag/pipeline.py").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run targeted tests to verify behavior still passes**

Run: `python -m pytest tests/test_intent_router.py tests/test_query_rewriter.py tests/test_clarification_generator.py tests/test_pipeline_conversations.py tests/test_api_conversations.py -q`
Expected: PASS before removing obsolete resolver references.

- [ ] **Step 3: Write minimal implementation**

```python
# Remove imports/usages of FollowupResolver and document semantic route behavior.
```

- [ ] **Step 4: Run the full targeted suite**

Run: `python -m pytest tests/test_intent_router.py tests/test_query_rewriter.py tests/test_clarification_generator.py tests/test_pipeline_conversations.py tests/test_api_conversations.py tests/test_llm_client.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md requirements.txt config/semantic_routes.json tests/test_intent_router.py tests/test_query_rewriter.py tests/test_clarification_generator.py tests/test_pipeline_conversations.py tests/test_api_conversations.py backend/rag/intent_router.py backend/rag/query_rewriter.py backend/rag/clarification_generator.py backend/rag/pipeline.py app.py
git rm backend/rag/followup_resolver.py
git commit -m "feat: replace followup resolution with semantic routing"
```
