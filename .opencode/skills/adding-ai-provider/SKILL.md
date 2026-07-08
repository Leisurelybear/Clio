---
name: adding-ai-provider
description: Use when adding or changing a Clio AI provider, registering models, configuring provider capability tags, adding OpenAI-compatible/Gemini adapters, or updating provider examples and validation.
---

# Adding a New AI Provider

## Workflow

1. Inspect `clio/ai/base.py`, `clio/ai/factory.py`, and the closest existing provider implementation.
2. Add or update the provider implementation under `clio/ai/`.
3. Register provider type lookup in `clio/ai/factory.py`.
4. Ensure lifecycle is explicit: cached providers must be closeable through `_clear_provider_cache()`.
5. Preserve retry semantics: `ProviderConfig.retry_attempts` means extra retries; `with_retry(attempts=...)` means total attempts, so pass `retry_attempts + 1`.
6. Add or update provider capability tags (`video`, `text`) in config examples and UI validation.
7. Update `config.example.yaml`, README docs, and relevant tests.

## Gemini Invariants

- Upload video once.
- Poll until the File API object is `ACTIVE`.
- Pass cancellation into polling.
- Generate content after activation.
- Delete the uploaded file in `finally`.

## Verification

Run focused tests first:

```bash
python -m pytest clio/tests/test_ai.py clio/tests/test_ai_gemini.py clio/tests/test_ai_openai_compat.py -q
python main.py check
```

Then run the full suite when the change affects shared config or routing.

## Common Mistakes

- Putting an actual API key in `api_key_env`; it must be the environment variable name.
- Adding a provider but not capability tags, making UI task binding ambiguous.
- Retrying uploads instead of only retrying wait/generate after a successful upload.
- Forgetting to update examples and README after user-visible provider changes.
