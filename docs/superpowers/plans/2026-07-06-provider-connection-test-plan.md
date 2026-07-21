# Provider Connection Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Settings UI button that verifies an AI provider/model by calling a new authenticated backend endpoint.

**Architecture:** Put provider test execution in a small service function, expose it through `POST /api/ai/test`, and wire the Global Settings provider cards to call that endpoint. The service reuses the existing provider factory and text generation path, so provider caching, proxy, retry, and key resolution stay centralized.

**Tech Stack:** Python 3.11+, stdlib HTTP server routes, existing `clio.ai` provider factory, frontend ES modules, pytest, Vitest where Node 18+ is available.

---

## File Structure

- Create `clio/ui/services/ai_test_service.py`: validates provider/model input, calls provider `generate_text()`, measures elapsed time, sanitizes errors.
- Create `clio/ui/routes/ai.py`: HTTP route handler for `POST /api/ai/test`.
- Modify `clio/ui/server.py`: import/register the new route and auth policy.
- Create `clio/tests/test_ai_test_service.py`: direct service tests.
- Create `clio/tests/test_ai_routes.py`: route handler tests.
- Modify `clio/tests/test_server.py`: dispatch and route-auth matrix coverage.
- Modify `clio/ui/static/src/editor-config.js`: add provider card test button, model selection, and status rendering.
- Modify existing frontend tests or add a focused Vitest file if local Node supports it.
- Modify `ROADMAP.md`: mark CR-008 provider/model test connection button complete.

---

### Task 1: Backend Service

**Files:**
- Create: `clio/ui/services/ai_test_service.py`
- Test: `clio/tests/test_ai_test_service.py`

- [ ] **Step 1: Write failing service tests**

Create `clio/tests/test_ai_test_service.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from clio.config import ProviderConfig, TaskConfig


def _config(*, models=None):
    provider = ProviderConfig(
        name="deepseek",
        type="openai",
        api_key="sk-secret-value",
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com/v1",
        models=models or ["deepseek-chat"],
    )
    return SimpleNamespace(
        ai=SimpleNamespace(
            providers={"deepseek": provider},
            tasks={"voiceover": TaskConfig(provider="deepseek", model="deepseek-chat")},
        )
    )


def test_unknown_provider_returns_failure():
    from clio.ui.services.ai_test_service import test_provider_connection

    result = test_provider_connection(_config(), provider_name="missing", model="x")

    assert result["ok"] is False
    assert "missing" in result["error"]


def test_multiple_models_require_model():
    from clio.ui.services.ai_test_service import test_provider_connection

    result = test_provider_connection(_config(models=["a", "b"]), provider_name="deepseek", model="")

    assert result["ok"] is False
    assert "model" in result["error"].lower()


def test_single_model_can_be_inferred(monkeypatch):
    fake_provider = MagicMock()
    fake_provider.generate_text.return_value.text = "ok"
    monkeypatch.setattr("clio.ui.services.ai_test_service.get_task_provider", lambda cfg, task: (fake_provider, "deepseek-chat"))

    from clio.ui.services.ai_test_service import test_provider_connection

    result = test_provider_connection(_config(models=["deepseek-chat"]), provider_name="deepseek", model="")

    assert result["ok"] is True
    assert result["model"] == "deepseek-chat"
    fake_provider.generate_text.assert_called_once()


def test_provider_exception_is_sanitized(monkeypatch):
    fake_provider = MagicMock()
    fake_provider.generate_text.side_effect = RuntimeError("bad key sk-secret-value")
    monkeypatch.setattr("clio.ui.services.ai_test_service.get_task_provider", lambda cfg, task: (fake_provider, "deepseek-chat"))

    from clio.ui.services.ai_test_service import test_provider_connection

    result = test_provider_connection(_config(), provider_name="deepseek", model="deepseek-chat")

    assert result["ok"] is False
    assert "sk-secret-value" not in result["error"]
    assert "***" in result["error"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest clio/tests/test_ai_test_service.py -q
```

Expected: fail because `clio.ui.services.ai_test_service` does not exist.

- [ ] **Step 3: Implement service**

Create `clio/ui/services/ai_test_service.py`:

```python
from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from clio.ai.factory import get_task_provider
from clio.config import AppConfig, TaskConfig
from clio.utils import mask_if_looks_like_key

_TEST_TASK = "__connection_test__"
_TEST_PROMPT = "Reply with exactly: ok"


def _sanitize_error(message: str, secrets: list[str]) -> str:
    result = message
    for secret in secrets:
        if secret:
            result = result.replace(secret, mask_if_looks_like_key(secret) or "***")
    return result


def test_provider_connection(config: AppConfig, *, provider_name: str, model: str | None = None) -> dict[str, Any]:
    provider_name = (provider_name or "").strip()
    model = (model or "").strip()
    provider_cfg = config.ai.providers.get(provider_name)
    if provider_cfg is None:
        return {"ok": False, "provider": provider_name, "model": model, "error": f"unknown provider: {provider_name}"}

    models = list(provider_cfg.models or [])
    if not model:
        if len(models) == 1:
            model = models[0]
        else:
            return {
                "ok": False,
                "provider": provider_name,
                "model": model,
                "error": "model is required when provider has zero or multiple registered models",
            }

    test_config = deepcopy(config)
    test_config.ai.tasks[_TEST_TASK] = TaskConfig(provider=provider_name, model=model)
    started = time.monotonic()
    try:
        provider, resolved_model = get_task_provider(test_config, _TEST_TASK)
        provider.generate_text(_TEST_PROMPT, resolved_model)
    except Exception as e:
        secrets = [provider_cfg.api_key, provider_cfg.api_key_env]
        return {
            "ok": False,
            "provider": provider_name,
            "model": model,
            "error": _sanitize_error(str(e), secrets),
        }

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "ok": True,
        "provider": provider_name,
        "model": model,
        "elapsed_ms": elapsed_ms,
        "message": "Connection test succeeded",
    }
```

- [ ] **Step 4: Run service tests**

Run:

```bash
python -m pytest clio/tests/test_ai_test_service.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add clio/ui/services/ai_test_service.py clio/tests/test_ai_test_service.py
git commit -m "feat(ui): add provider connection test service"
```

---

### Task 2: HTTP Route and Server Dispatch

**Files:**
- Create: `clio/ui/routes/ai.py`
- Modify: `clio/ui/server.py`
- Test: `clio/tests/test_ai_routes.py`
- Test: `clio/tests/test_server.py`

- [ ] **Step 1: Write failing route tests**

Create `clio/tests/test_ai_routes.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock


def test_ai_test_route_validates_provider(monkeypatch):
    from clio.ui.routes.ai import handle_post_ai_test

    handler = MagicMock()
    handle_post_ai_test(handler, {}, {})

    handler._send_json.assert_called_once()
    body, status = handler._send_json.call_args.args
    assert status == 400
    assert body["ok"] is False


def test_ai_test_route_calls_service(monkeypatch):
    from clio.ui.routes.ai import handle_post_ai_test

    handler = MagicMock()
    handler._resolve_project_input.return_value = "project"
    handler._get_config.return_value = "config"
    monkeypatch.setattr(
        "clio.ui.routes.ai.test_provider_connection",
        lambda cfg, provider_name, model=None: {"ok": True, "provider": provider_name, "model": model},
    )

    handle_post_ai_test(handler, {"project": ["demo"]}, {"provider": "deepseek", "model": "deepseek-chat"})

    handler._send_json.assert_called_once_with({"ok": True, "provider": "deepseek", "model": "deepseek-chat"})
```

Modify `clio/tests/test_server.py` with one dispatch test in `TestDoPOST`:

```python
    @patch("clio.ui.server.handle_post_ai_test")
    def test_post_ai_test(self, mock_fn, handler_cls):
        handler = self._post_handler(handler_cls, {"provider": "deepseek"}, "/api/ai/test")
        handler.do_POST()
        mock_fn.assert_called_once()
```

Add auth matrix row:

```python
            ("POST", "/api/ai/test", True),
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest clio/tests/test_ai_routes.py clio/tests/test_server.py -q
```

Expected: fail because route module/import/dispatch is missing.

- [ ] **Step 3: Implement route**

Create `clio/ui/routes/ai.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clio.ui.services.ai_test_service import test_provider_connection

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def handle_post_ai_test(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    provider = (obj.get("provider") or "").strip()
    model = (obj.get("model") or "").strip()
    if not provider:
        return handler._send_json({"ok": False, "error": "provider is required"}, 400)

    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)
    result = test_provider_connection(cfg, provider_name=provider, model=model)
    handler._send_json(result)
```

- [ ] **Step 4: Register route**

Modify `clio/ui/server.py`:

```python
from clio.ui.routes.ai import handle_post_ai_test
```

Add policy:

```python
    RoutePolicy("POST", "/api/ai/test"),
```

Add `do_POST` branch before unknown endpoint:

```python
            if path == "/api/ai/test":
                return handle_post_ai_test(self, qs, obj)
```

- [ ] **Step 5: Run backend route tests**

Run:

```bash
python -m pytest clio/tests/test_ai_test_service.py clio/tests/test_ai_routes.py clio/tests/test_server.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add clio/ui/routes/ai.py clio/ui/server.py clio/tests/test_ai_routes.py clio/tests/test_server.py
git commit -m "feat(ui): expose provider connection test endpoint"
```

---

### Task 3: Frontend Provider Card UI

**Files:**
- Modify: `clio/ui/static/src/editor-config.js`
- Test: existing frontend tests if Node 18+ is available

- [ ] **Step 1: Add provider-card status markup**

In `_renderProviderList()`, add a test button and status area inside each provider card:

```javascript
          <button class="btn-provider-test" data-provider="${escapeHtml(name)}">测试</button>
```

Place it in `.provider-card-actions` before edit/delete, and add this after `.provider-card-body`:

```javascript
      <div class="provider-test-status" data-provider-status="${escapeHtml(name)}"></div>
```

- [ ] **Step 2: Add handler wiring**

In `_attachProviderListHandlers(...)`, add:

```javascript
  pane.querySelectorAll('.btn-provider-test').forEach(btn => {
    btn.onclick = () => _testProvider(providersObj, btn.dataset.provider);
  });
```

- [ ] **Step 3: Implement `_testProvider` helper**

Add near provider modal helpers:

```javascript
async function _testProvider(providersObj, providerName) {
  const provider = providersObj[providerName];
  const status = document.querySelector(`[data-provider-status="${CSS.escape(providerName)}"]`);
  const btn = document.querySelector(`.btn-provider-test[data-provider="${CSS.escape(providerName)}"]`);
  if (!provider || !status || !btn) return;

  const models = provider.models || [];
  let model = models[0] || '';
  if (models.length > 1) {
    model = prompt('选择要测试的模型：\n' + models.join('\n'), models[0]) || '';
    model = model.trim();
    if (!model) return;
  }

  btn.disabled = true;
  btn.textContent = '测试中...';
  status.className = 'provider-test-status muted';
  status.textContent = model ? `正在测试 ${model}...` : '正在测试...';
  try {
    const result = await api('POST', '/api/ai/test', { provider: providerName, model });
    if (result.ok) {
      status.className = 'provider-test-status ok';
      status.textContent = `连接成功 (${result.elapsed_ms || 0} ms)`;
    } else {
      status.className = 'provider-test-status err';
      status.textContent = result.error || '连接测试失败';
    }
  } catch (e) {
    status.className = 'provider-test-status err';
    status.textContent = e.message || '连接测试失败';
  } finally {
    btn.disabled = false;
    btn.textContent = '测试';
  }
}
```

- [ ] **Step 4: Run frontend test command if possible**

Run:

```bash
npm test -- --run clio/ui/static/src/__tests__/editor-config.test.js
```

Expected on Node 18+: relevant tests pass. Expected on local Node 16: Vite startup fails with `node:fs/promises` missing `constants`; record this in verification notes.

- [ ] **Step 5: Commit**

```bash
git add clio/ui/static/src/editor-config.js
git commit -m "feat(ui): add provider test button"
```

---

### Task 4: Roadmap and Verification

**Files:**
- Modify: `ROADMAP.md`

- [ ] **Step 1: Update roadmap**

In `ROADMAP.md`, under CR-008:

```markdown
  - [x] Add provider/model test connection button.
```

- [ ] **Step 2: Run Python verification**

Run:

```bash
python -m ruff check clio main.py
python -m pytest clio/tests/ -q
```

Expected: ruff passes and all Python tests pass.

- [ ] **Step 3: Run frontend verification**

Run:

```bash
node -v
npm test -- --run clio/ui/static/src/__tests__/editor-config.test.js
```

Expected on Node 18+: frontend tests pass. If local Node is 16, record the Vite startup incompatibility and do not claim frontend tests passed.

- [ ] **Step 4: Commit roadmap**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): mark provider connection test complete"
```

---

## Self-Review

- Spec coverage: backend endpoint, UI button, model selection, error sanitization, auth policy, tests, and roadmap are covered.
- Placeholder scan: no unfinished markers or unspecified implementation steps remain.
- Type consistency: service uses `provider_name`, route receives `provider`, UI sends `{ provider, model }`, and all names match the spec.
