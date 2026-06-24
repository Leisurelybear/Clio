---
name: adding-ai-provider
description: Use when adding a new AI provider, registering a model, configuring API access for a new LLM/video service
---

# Adding a New AI Provider

## Overview

A new AI provider needs an implementation file, registration in the provider factory, config example, and documentation.

## Implementation

1. Create `vlog_tool/ai/<name>.py` implementing `TextAIProvider` and/or `VideoAIProvider` from `base.py`
2. Register in `vlog_tool/ai/factory.py:_PROVIDER_TYPES`
3. Add example config in `config.example.yaml`
4. Verify with `python main.py check` (auto-lists all registered providers)
5. Update README (CN/EN) with usage instructions

## Common Mistakes

- Forgetting to add the provider to `_PROVIDER_TYPES` — `main.py check` will not list it
- API key in `api_key_env` field instead of env var name — use `mask_if_looks_like_key()` guard
- Missing retry wrapping — both Gemini and OpenAI-compat use `with_retry()`
