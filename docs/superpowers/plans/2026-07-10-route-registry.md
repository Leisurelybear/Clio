# A-007: Route Registry Implementation Plan

**Goal:** Replace server.py hand-written route if-chains with a declarative `Router` class.

**Architecture:** New `clio/ui/router.py` with `Route` dataclass + `Router` class that compiles path patterns to regex, dispatches method+path to handler, and supports `{param}` path parameters. Server.py do_GET/do_PUT/do_POST/do_DELETE if-chains replaced with `router.dispatch()` calls.

**Tech Stack:** Python stdlib (`re`, `dataclasses`, `inspect`), no new dependencies.

---

### Task 1: Write `test_router.py`

**Files:**
- Create: `clio/tests/test_router.py`

- [x] **Step 1: Write the test file**

```python
"""Tests for clio/ui/router.py — Route, Router, dispatch."""
from __future__ import annotations

from clio.ui.router import Route, Router


def _handler_dummy(self, qs):
    return "dummy"


def _handler_with_param(self, qs, name):
    return f"param:{name}"


def _handler_no_qs(self, obj):
    return f"body:{obj}"


class TestRoute:
    def test_static_route(self):
        router = Router()
        router.add(Route("GET", "/api/config", _handler_dummy))
        handler, kwargs, route = router.dispatch("GET", "/api/config")
        assert handler is _handler_dummy
        assert kwargs == {}
        assert route is not None

    def test_param_route(self):
        router = Router()
        router.add(Route("GET", "/api/vmeta/{stem}", _handler_with_param))
        handler, kwargs, route = router.dispatch("GET", "/api/vmeta/GL010695")
        assert handler is _handler_with_param
        assert kwargs == {"stem": "GL010695"}

    def test_param_route_multiple(self):
        router = Router()
        router.add(Route("PUT", "/api/prompts/{name}", _handler_with_param))
        handler, kwargs, route = router.dispatch("PUT", "/api/prompts/day1")
        assert handler is _handler_with_param
        assert kwargs == {"name": "day1"}

    def test_no_match_returns_none(self):
        router = Router()
        router.add(Route("GET", "/api/config", _handler_dummy))
        handler, kwargs, route = router.dispatch("GET", "/api/unknown")
        assert handler is None

    def test_method_mismatch_returns_none(self):
        router = Router()
        router.add(Route("GET", "/api/config", _handler_dummy))
        handler, kwargs, route = router.dispatch("POST", "/api/config")
        assert handler is None

    def test_prefix_route(self):
        router = Router()
        router.add(Route("GET", "/static/", _handler_dummy, prefix=True))
        handler, kwargs, route = router.dispatch("GET", "/static/js/app.js")
        assert handler is _handler_dummy
        assert kwargs == {}

    def test_prefix_route_exact_path(self):
        router = Router()
        router.add(Route("GET", "/", _handler_dummy, prefix=False))
        handler, kwargs, route = router.dispatch("GET", "/")
        assert handler is _handler_dummy

    def test_add_list(self):
        router = Router()
        router.add_list([
            Route("GET", "/api/config", _handler_dummy),
            Route("GET", "/api/videos", _handler_dummy),
        ])
        h1, _, _ = router.dispatch("GET", "/api/config")
        h2, _, _ = router.dispatch("GET", "/api/videos")
        assert h1 is _handler_dummy
        assert h2 is _handler_dummy

    def test_get_policy_returns_route_policy(self):
        router = Router()
        router.add(Route("GET", "/api/config", _handler_dummy, auth_required=True))
        policy = router.get_policy("GET", "/api/config")
        assert policy.auth_required is True

    def test_get_policy_prefix(self):
        router = Router()
        router.add(Route("GET", "/static/", _handler_dummy, auth_required=False, prefix=True))
        policy = router.get_policy("GET", "/static/js/app.js")
        assert policy.auth_required is False

    def test_get_policy_unknown_returns_default_auth(self):
        router = Router()
        policy = router.get_policy("GET", "/api/unknown")
        assert policy.auth_required is True
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest clio/tests/test_router.py -x --tb=short -q`
Expected: FAIL (no module named `clio.ui.router`)

### Task 2: Implement `router.py`

**Files:**
- Create: `clio/ui/router.py`

- [ ] **Step 1: Write minimal implementation**

```python
"""URL routing for the UI server.

Replaces hand-written if-chains in server.py with a declarative Router.
Supports static routes, {param} path parameters, and prefix matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class RoutePolicy:
    method: str
    path: str
    auth_required: bool = True
    prefix: bool = False


@dataclass
class Route:
    method: str
    path: str
    handler: Callable
    auth_required: bool = True
    prefix: bool = False


class Router:
    def __init__(self) -> None:
        self._routes: dict[str, list[tuple[re.Pattern, list[str], Route]]] = {}

    def add(self, route: Route) -> None:
        pattern, param_names = self._compile(route.path)
        self._routes.setdefault(route.method, []).append((pattern, param_names, route))

    def add_list(self, routes: list[Route]) -> None:
        for r in routes:
            self.add(r)

    def dispatch(
        self, method: str, path: str
    ) -> tuple[Callable | None, dict[str, str], Route | None]:
        for pattern, param_names, route in self._routes.get(method, []):
            if route.prefix:
                if path.startswith(route.path):
                    return route.handler, {}, route
            else:
                m = pattern.match(path)
                if m:
                    kwargs = dict(zip(param_names, m.groups()))
                    return route.handler, kwargs, route
        return None, {}, None

    def get_policy(self, method: str, path: str) -> RoutePolicy:
        _, _, route = self.dispatch(method, path)
        if route is not None:
            return RoutePolicy(
                method=route.method,
                path=route.path,
                auth_required=route.auth_required,
                prefix=route.prefix,
            )
        return RoutePolicy(method, path, auth_required=_is_api_path(path))

    @staticmethod
    def _compile(path: str) -> tuple[re.Pattern, list[str]]:
        param_names: list[str] = []

        def _replace_param(m: re.Match) -> str:
            name = m.group(1)
            param_names.append(name)
            return r"([^/]+)"

        regex_str = re.sub(r"\{(\w+)\}", _replace_param, re.escape(path))
        return re.compile(f"^{regex_str}$"), param_names


def _is_api_path(path: str) -> bool:
    return path.startswith("/api/")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest clio/tests/test_router.py -x --tb=short -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add clio/ui/router.py clio/tests/test_router.py
git commit -m "feat(router): add Router class with dispatch and path params (A-007 Task 1-2)"
```

### Task 3: Replace server.py do_GET if-chain

**Files:**
- Modify: `clio/ui/server.py`

- [ ] **Step 1: Register GET routes in server.py**

In `make_handler()`, after building `_ROUTE_POLICIES` (or replacing it), build a `Router` with all GET routes:

```python
router = Router()
router.add_list([
    # Public routes
    Route("GET", "/", handle_index, auth_required=False),
    Route("GET", "/index.html", handle_index, auth_required=False),
    Route("GET", "/favicon.ico", handle_favicon, auth_required=False),
    Route("GET", "/static/", handle_static, auth_required=False, prefix=True),
    # API routes
    Route("GET", "/api/config", handle_get_config),
    Route("GET", "/api/config/raw", handle_get_config_raw),
    Route("GET", "/api/config/global", handle_get_config_global),
    Route("GET", "/api/config/project", handle_get_config_project),
    Route("GET", "/api/providers", handle_get_providers),
    Route("GET", "/api/project", handle_get_project),
    Route("GET", "/api/projects", handle_get_projects),
    Route("GET", "/api/videos", handle_get_videos),
    Route("GET", "/api/video", handle_get_video),
    Route("GET", "/api/vmeta/{stem}", handle_get_vmeta),
    Route("GET", "/api/texts", handle_get_texts),
    Route("GET", "/api/voiceover", handle_get_voiceover),
    Route("GET", "/api/plans", handle_get_plans),
    Route("GET", "/api/run/status", handle_get_run_status),
    Route("GET", "/api/run/stream", handle_get_run_stream),
    Route("GET", "/api/plan", handle_get_plan),
    Route("GET", "/api/processing-state", handle_get_processing_state),
    Route("GET", "/api/fs/dirs", handle_get_fs_dirs),
    Route("GET", "/api/transcripts", handle_get_transcripts),
    Route("GET", "/api/whisper/check", handle_get_whisper_check),
    Route("GET", "/api/whisper/install/status", handle_get_whisper_install_status),
    Route("GET", "/api/whisper/models", handle_get_whisper_models),
    Route("GET", "/api/token-usage", handle_get_token_usage),
    Route("GET", "/api/env", handle_get_env),
    Route("GET", "/api/prompts", handle_get_prompts),
    Route("GET", "/api/logs", handle_get_logs),
])
```

Replace `do_GET`:

```python
def do_GET(self):
    url = urlparse(self.path)
    qs = parse_qs(url.query)
    path = url.path

    # Static routes still handled directly (no auth/QS parsing needed)
    if path in ("/", "/index.html"):
        return handle_index(self)
    if path == "/favicon.ico":
        return handle_favicon(self)
    if path.startswith("/static/"):
        rel = path[len("/static/") :]
        return handle_static(self, rel)

    handler_fn, path_kwargs, route = router.dispatch("GET", path)
    if handler_fn is None:
        return self.send_error(HTTPStatus.NOT_FOUND)

    if route and route.auth_required and not self._require_auth():
        return

    if path_kwargs:
        return handler_fn(self, qs, **path_kwargs)
    return handler_fn(self, qs)
```

Replace `_get_requires_auth` to use `router.get_policy()`:

```python
def _get_requires_auth(path: str, method: str = "GET") -> bool:
    policy = router.get_policy(method, path)
    return policy.auth_required
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest clio/tests/test_server.py -x --tb=short -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add clio/ui/server.py
git commit -m "feat(router): replace do_GET if-chain with router.dispatch (A-007 Task 3)"
```

### Task 4: Replace do_PUT / do_POST / do_DELETE if-chains

**Files:**
- Modify: `clio/ui/server.py`

- [ ] **Step 1: Register PUT/POST/DELETE routes and replace if-chains**

Add to the `router.add_list()` call:

```python
# PUT
Route("PUT", "/api/config/raw", handle_put_config_raw),
Route("PUT", "/api/config/global", handle_put_config_global),
Route("PUT", "/api/config/project", handle_put_config_project),
Route("PUT", "/api/providers/{name}", handle_put_provider),
Route("PUT", "/api/project", handle_put_project),
Route("PUT", "/api/texts", handle_put_texts),
Route("PUT", "/api/voiceover", handle_put_voiceover),
Route("PUT", "/api/plan", handle_put_plan),
Route("PUT", "/api/transcripts", handle_put_transcripts),
Route("PUT", "/api/whisper/model", handle_put_whisper_model),
Route("PUT", "/api/env", handle_put_env),
Route("PUT", "/api/prompts/{name}", handle_put_prompt),
# POST
Route("POST", "/api/run/start", handle_post_run_start),
Route("POST", "/api/webhook/trigger", handle_post_run_start),
Route("POST", "/api/run/preview", handle_post_run_preview),
Route("POST", "/api/run/cancel", handle_post_run_cancel),
Route("POST", "/api/ai/test", handle_post_ai_test),
Route("POST", "/api/config/init", handle_post_config_init),
Route("POST", "/api/providers", handle_post_provider),
Route("POST", "/api/cut", handle_post_cut),
Route("POST", "/api/refine", handle_post_refine),
Route("POST", "/api/export", handle_post_export),
Route("POST", "/api/project/create", handle_post_project_create),
Route("POST", "/api/project/add", handle_post_project_add),
Route("POST", "/api/project/remove", handle_post_project_remove),
Route("POST", "/api/rerun", handle_post_rerun),
Route("POST", "/api/transcripts", handle_post_transcripts),
Route("POST", "/api/whisper/install", handle_post_whisper_install),
Route("POST", "/api/whisper/install/cancel", handle_post_whisper_install_cancel),
Route("POST", "/api/whisper/models/delete", handle_post_whisper_model_delete),
Route("POST", "/api/logs/clear", handle_post_logs_clear),
# DELETE
Route("DELETE", "/api/prompts/{name}", handle_delete_prompt),
Route("DELETE", "/api/providers/{name}", handle_delete_provider),
```

Replace `do_PUT`:

```python
def do_PUT(self):
    url = urlparse(self.path)
    qs = parse_qs(url.query)
    path = url.path
    length = int(self.headers.get("Content-Length", 0))
    raw = self.rfile.read(length) if length else b""
    try:
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("expected a JSON object")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
        return self._send_json({"ok": False, "error": f"invalid JSON: {e}"}, 400)

    handler_fn, path_kwargs, route = router.dispatch("PUT", path)
    if handler_fn is None:
        return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    if route and route.auth_required and not self._require_auth():
        return

    if path_kwargs:
        return handler_fn(self, qs, obj, **path_kwargs)
    return handler_fn(self, qs, obj)
```

Replace `do_POST`:

```python
def do_POST(self):
    url = urlparse(self.path)
    qs = parse_qs(url.query)
    path = url.path
    length = int(self.headers.get("Content-Length", 0))
    raw = self.rfile.read(length) if length else b""
    try:
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("expected a JSON object")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
        return self._send_json({"ok": False, "error": f"invalid JSON: {e}"}, 400)

    handler_fn, path_kwargs, route = router.dispatch("POST", path)
    if handler_fn is None:
        return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    if route and route.auth_required and not self._require_auth():
        return

    # Handlers have varying signatures: some take qs, some take obj, some take both
    sig = _handler_signature(handler_fn)
    args = {"self": self}
    if "qs" in sig:
        args["qs"] = qs
    if "obj" in sig:
        args["obj"] = obj
    args.update(path_kwargs)
    return handler_fn(**args)
```

Replace `do_DELETE`:

```python
def do_DELETE(self):
    url = urlparse(self.path)
    qs = parse_qs(url.query)
    path = url.path
    if not self._require_auth():
        return

    handler_fn, path_kwargs, route = router.dispatch("DELETE", path)
    if handler_fn is None:
        return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)
    return handler_fn(self, qs, **path_kwargs)
```

Add helper:

```python
def _handler_signature(handler: Callable) -> set[str]:
    """Return set of parameter names accepted by handler."""
    import inspect
    return {p.name for p in inspect.signature(handler).parameters.values() if p.name != "self"}
```

Handle `/api/logs` and `/api/logs/clear` specially (they don't fit the handler pattern). The `handle_get_logs` function becomes a wrapper in server.py:

```python
def handle_get_logs(handler, qs):
    offset = int(qs.get("offset", ["0"])[0])
    return handler._send_json(read_session_log(offset))


def handle_post_logs_clear(handler, qs, obj):
    clear_session_log()
    return handler._send_json({"ok": True})
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest clio/tests/test_server.py -x --tb=short -q`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest clio/tests/ -x --tb=short -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add clio/ui/server.py
git commit -m "feat(router): replace do_PUT/do_POST/do_DELETE if-chains with router.dispatch (A-007 Task 4)"
```

### Task 5: Clean up

**Files:**
- Modify: `clio/ui/server.py`

- [ ] **Step 1: Remove `_ROUTE_POLICIES` and `RoutePolicy` from server.py**

Since `RoutePolicy` is now in `router.py` and policies are derived from router registrations, remove from server.py:
- `RoutePolicy` dataclass
- `_ROUTE_POLICIES` tuple
- `_ROUTE_POLICY_BY_METHOD_PATH` dict
- `_get_route_policy()` function
- `_get_requires_auth()` function (replaced by `router.get_policy()`)

- [ ] **Step 2: Clean up imports**

Remove unused imports from server.py (ones only used by old routing logic).

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest clio/tests/ -x --tb=short -q`
Expected: PASS

- [ ] **Step 4: Ruff check**

Run: `python -m ruff check clio/ui/server.py clio/ui/router.py clio/tests/test_router.py`
Expected: All checks passed!

- [ ] **Step 5: Commit**

```bash
git add clio/ui/server.py
git commit -m "refactor(router): remove _ROUTE_POLICIES, clean up unused imports (A-007 Task 5)"
```
