# Provider Connection Test Design

## Goal

Add a small, explicit connection test for AI providers in the Settings UI. Users should be able to verify that a provider's API key, base URL, proxy, and selected model work before running the full video pipeline.

This belongs to CR-008 UX/observability follow-ups.

## Scope

In scope:

- Backend endpoint: `POST /api/ai/test`
- Global Settings provider card test button
- Model selection for providers with multiple registered models
- Focused backend and UI behavior tests where the current test runtime allows it
- ROADMAP update after implementation

Out of scope:

- Video upload or Gemini File API testing
- Automatic periodic provider health checks
- Persisting provider health status in config files
- Creating provider-specific backend APIs for each adapter

## Backend API

### Request

```json
{
  "provider": "deepseek",
  "model": "deepseek-chat"
}
```

Rules:

- `provider` is required and must exist in the active global config.
- `model` is required unless the provider has exactly one registered model, in which case the backend may use that model.
- The endpoint uses the active project context only for normal config resolution/auth; provider definitions stay global.
- The endpoint must require the same API authentication policy as other write/action endpoints.

### Execution

The backend reuses existing provider construction and calls `generate_text()` with a minimal prompt. A suitable prompt is:

```text
Reply with exactly: ok
```

The endpoint should not call `analyze_video()` and should not upload files to Gemini. Gemini is tested through its text generation path only.

Provider lifecycle must use the existing cache semantics. If a provider object is created through the factory, it can remain cached according to `provider_ttl_min`; the endpoint should not add a parallel cache.

### Response

Success:

```json
{
  "ok": true,
  "provider": "deepseek",
  "model": "deepseek-chat",
  "elapsed_ms": 742,
  "message": "Connection test succeeded"
}
```

Failure:

```json
{
  "ok": false,
  "provider": "deepseek",
  "model": "deepseek-chat",
  "error": "API returned 401: invalid API key"
}
```

Errors must be sanitized. API keys and values that look like keys must never be returned.

## UI Behavior

Global Settings provider cards get a `Test` button next to edit/delete actions.

Behavior:

- If the provider has one model, clicking `Test` immediately tests that model.
- If the provider has multiple models, clicking `Test` opens a small model selector or inline dropdown before starting.
- While testing, disable the button and show a short pending state.
- On success, show a compact success message with elapsed time.
- On failure, show the backend error message in the provider card area and keep the provider editable.

The Project task-binding tab does not need a separate button in this iteration. Users can validate task-bound models by testing the provider/model from the Global tab.

## Error Handling

Map common failures into actionable messages:

- Missing API key: tell the user to set the provider's env var or API key.
- Invalid base URL or connection failure: mention endpoint/network/proxy.
- 401/403: mention invalid or unauthorized key.
- 404: mention model name or provider endpoint mismatch.
- 429: mention rate limit/quota.
- Timeout: mention network/provider latency.

All error messages should pass through existing key masking helpers where possible.

## Tests

Backend tests:

- Unknown provider returns a structured failure.
- Missing model is rejected when the provider has multiple models.
- Single-model provider can omit `model`.
- Successful provider call returns `ok: true` and elapsed time.
- Provider exception returns `ok: false` with sanitized error.
- Auth policy covers the new route in token mode.

Frontend tests:

- Provider card renders a test button.
- Clicking a one-model provider calls `/api/ai/test`.
- Multiple-model providers require model choice.
- Success and failure states render in the card.

Local note: frontend Vitest requires Node 18 or newer. If the local runtime is still Node 16, document the frontend test command as not runnable locally and rely on CI-compatible Node.

## Implementation Notes

Recommended backend shape:

- Add route handler under `clio/ui/routes/ai.py` or another focused route module.
- Register `POST /api/ai/test` in the server route table/dispatch.
- Keep the actual connection-test logic in a small service function so it can be unit-tested without HTTP handler ceremony.

Recommended frontend shape:

- Extend `editor-config.js` provider cards with a test button and small status area.
- Reuse the existing `api()` wrapper so token handling remains centralized.
- Keep UI state local to each card; do not store test results in config.

