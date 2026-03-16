# Chat Markdown And Streaming Design

**Date:** 2026-03-17

## Goal

Improve the chat experience by rendering assistant responses as Markdown in the frontend and by streaming LLM output token-by-token so users can see answers arrive incrementally.

## Current State

- The frontend renders both user and assistant messages as escaped plain text in [`frontend/app.js`](/Users/zzz/RschProjects/stockReportRAG/frontend/app.js).
- The backend exposes only a blocking JSON chat endpoint in [`app.py`](/Users/zzz/RschProjects/stockReportRAG/app.py).
- The RAG pipeline in [`backend/rag/pipeline.py`](/Users/zzz/RschProjects/stockReportRAG/backend/rag/pipeline.py) generates one final answer string, then persists the full turn.
- The LLM client in [`backend/rag/llm_client.py`](/Users/zzz/RschProjects/stockReportRAG/backend/rag/llm_client.py) does not expose streaming.

## Requirements

- Render Markdown only for assistant messages.
- Keep user messages as plain text.
- Add LLM streaming for chat replies.
- Preserve existing conversation persistence and history loading.
- Keep the current non-streaming endpoint available for compatibility and tests.
- Show structured sources after the streamed answer completes.
- Avoid unsafe HTML injection from model output.

## Chosen Approach

Add a new streaming chat endpoint while keeping the existing blocking endpoint unchanged. Extend the LLM client and pipeline with streaming helpers that emit incremental answer text, then persist the completed assistant message once generation finishes. Update the frontend to prefer the streaming endpoint, render assistant content as sanitized Markdown, and progressively update a placeholder assistant bubble during generation.

This keeps the current data model and conversation history format intact while isolating the new behavior behind a narrow interface.

## Alternatives Considered

### 1. New streaming endpoint plus frontend incremental rendering

This is the chosen approach. It minimizes regression risk because existing JSON callers continue to work and only the interactive chat path changes.

### 2. Replace the existing `/chat` endpoint with streaming

Rejected because it would break current tests and any code expecting a final JSON payload.

### 3. Introduce WebSocket transport

Rejected because the product only needs one-way streaming for request/response chat, so WebSocket complexity is unnecessary.

## Architecture

### Backend API

Keep `POST /api/projects/{project_name}/chat` as-is. Add `POST /api/projects/{project_name}/chat/stream` that returns a streaming response.

The stream will emit newline-delimited JSON events with these types:

- `start`: confirms the resolved `conversation_id`
- `delta`: contains a text fragment to append to the current assistant message
- `sources`: contains the final structured source list
- `done`: signals successful completion
- `error`: signals a recoverable generation failure for the UI

The response content type can be `application/x-ndjson`, which matches the actual payload shape and is easy to parse with `fetch()` streams.

### Pipeline And Persistence

The pipeline will share retrieval and prompt construction between blocking and streaming code paths. For streaming:

1. Resolve or create the conversation ID.
2. Retrieve source chunks.
3. If there are no chunks, emit a single final answer without calling the LLM.
4. Otherwise call the LLM streaming API and accumulate the emitted text.
5. Strip any model-generated source section from the final text.
6. Persist the user message and the completed assistant message only after the stream finishes.
7. Emit `sources` and `done`.

This avoids writing partial assistant output into conversation storage.

### Frontend Rendering

The frontend sends chat messages through the streaming endpoint. It immediately appends the user message locally, then inserts an empty assistant placeholder. As `delta` events arrive, it updates the placeholder content and rerenders assistant Markdown.

Assistant Markdown rendering must be sanitized before insertion. User messages remain escaped plain text.

Conversation history loaded from disk will use the same rendering logic, so the final view stays consistent with streamed output.

## Component Changes

### [`backend/rag/llm_client.py`](/Users/zzz/RschProjects/stockReportRAG/backend/rag/llm_client.py)

- Add a streaming method around the OpenAI-compatible client.
- Yield text deltas only.
- Keep existing non-streaming methods unchanged.

### [`backend/rag/pipeline.py`](/Users/zzz/RschProjects/stockReportRAG/backend/rag/pipeline.py)

- Extract shared answer-generation setup so blocking and streaming paths do not duplicate retrieval and source construction.
- Add a streaming generator that yields typed events and persists the final turn.

### [`app.py`](/Users/zzz/RschProjects/stockReportRAG/app.py)

- Add the streaming chat route and wrap the pipeline generator in `StreamingResponse`.

### [`frontend/index.html`](/Users/zzz/RschProjects/stockReportRAG/frontend/index.html)

- Load a lightweight Markdown parser and sanitizer from local static assets or a vendored browser bundle.

### [`frontend/app.js`](/Users/zzz/RschProjects/stockReportRAG/frontend/app.js)

- Split message rendering into user plain-text rendering and assistant Markdown rendering.
- Add stream reader logic for NDJSON events.
- Track in-progress assistant messages and final sources.
- Preserve current conversation refresh behavior.

### [`frontend/styles.css`](/Users/zzz/RschProjects/stockReportRAG/frontend/styles.css)

- Add readable Markdown styles for headings, lists, code, blockquotes, and tables inside assistant bubbles.

## Error Handling

- If the stream returns an `error` event or terminates unexpectedly, the placeholder assistant bubble will be replaced with a concise failure message.
- The frontend should avoid caching failed partial assistant content into `state.conversationDetails`.
- The backend should not persist assistant output if generation fails before completion.
- Retrieval-empty cases are not errors; they produce one complete assistant message and empty sources.

## Testing Strategy

### Backend

- Add API tests for the new streaming endpoint, including normal completion and zero-result behavior.
- Add LLM client tests for streaming delta extraction using a fake OpenAI response stream.
- Add pipeline tests that verify conversation persistence occurs only after stream completion.

### Frontend

- No frontend test harness exists today, so cover rendering and stream parsing with focused helper functions that are easy to reason about and manually verify in-browser.

## Risks

- Frequent Markdown rerendering during streaming can cause UI jank if updates are too granular.
- Some providers may emit empty or irregular stream chunks; the client must ignore non-text deltas safely.
- Markdown libraries must be sanitized to prevent unsafe HTML injection.

## Success Criteria

- Assistant responses display formatted Markdown in the chat UI.
- Users can see assistant text appear incrementally during generation.
- Completed conversations still reload correctly from persisted JSON files.
- Existing non-streaming behavior and tests remain intact.
