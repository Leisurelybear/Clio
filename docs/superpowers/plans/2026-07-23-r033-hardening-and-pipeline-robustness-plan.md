# R-033 Hardening + Pipeline Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship R-033a–e security/capability hardening plus pipeline correctness fixes (I1/I3/I4/I7/I8), export/run path safety, cancel partial cleanup, and waveform abspath parity — no new product features.

**Architecture:** Reuse existing helpers (`_is_safe_basename`, `resolve_project_input` allowlist pattern, `_matches_selected_artifact`). Add small pure helpers for path sandbox and secret masking; tighten route handlers and task loops; one feature per commit with mock-style tests.

**Tech Stack:** Python 3.11+ / pytest / unittest.mock; stdlib `http.server`; no frontend build for most tasks (Wave6b is Python-only).

**Spec:** `docs/superpowers/specs/2026-07-23-r033-hardening-and-pipeline-robustness-design.md`

## Global Constraints

- One feature per commit; English commit messages; Chinese UI/log copy OK.
- Tests: mock/monkeypatch style; run subset then full `python -m pytest clio/tests/ -q` before final ROADMAP commit.
- Do not implement non-goals (R-032/025/031b/027e/028, I9/I11–I15, cut prefix glob, Jianying expand, create `output_dir`).
- Body cap = **8 MiB**; token compare = `hmac.compare_digest` only when equal-length strings.
- Runtime API keys: **env-first, yaml fallback** (keep `_resolve_api_key`); write strip + GET mask.
- Global validate numeric floors: **`>= 0`** (match `_validate_config`), not `timeout_sec > 0`.
- Work on `main` directly; do not push unless user asks.

---

## File map

| File | Responsibility |
| --- | --- |
| `clio/log.py` | Skip blank `session_log` writes |
| `clio/ui/routes/export.py` | Safe `day` basename |
| `clio/ui/routes/run.py` | Safe `day_label`; deepcopy cfg; sandboxed `project_dir` |
| `clio/ui/services/project_service.py` | Shared allowlist helper for project dirs |
| `clio/tasks/cut.py` | Sandbox `output_dir` under `paths.output_dir`; safer `replace_file_safely` |
| `clio/ui/routes/plan.py` | Surface cut sandbox 400 |
| `clio/ui/server.py` | Body size cap; `compare_digest` auth |
| `clio/config/validators.py` | `validate_global_config` |
| `clio/config/loader.py` | Call validate on global load |
| `clio/ui/routes/config_routes.py` | Strip api_key on write; mask on GET/responses |
| `clio/ai/gemini.py`, `clio/doctor.py`, `clio/main.py` | Env-only key error copy |
| `clio/tasks/_helpers.py` | (tests only for R-033e) |
| `clio/tasks/plan.py` | Honor `files=` |
| `clio/tasks/label.py` | State key from source/compressed |
| `clio/tasks/scripts.py` | Serial try/except |
| `clio/tasks/refine.py` | Return `completed` |
| `clio/progress.py` | Reset `_start` on phase change |
| `clio/compress.py` / `clio/tasks/compress.py` | Unlink partial on cancel/fail |
| `clio/ui/routes/waveform.py` | Strict abspath allowlist |
| `clio/tests/*` | Per-task tests |
| `ROADMAP.md` | Mark R-033 done + note pipeline fixes |

---

### Task 0: Session log blank rows (Wave0)

**Files:**
- Modify: `clio/log.py` (working tree already has fix)
- Modify: `clio/tests/test_log.py` (working tree already has test)

**Interfaces:**
- Produces: `_TeeWriter.write` only `session_log.write` when `message.rstrip()` non-empty

- [ ] **Step 1: Confirm working tree matches design**

```python
# clio/log.py inside write(), after logger branch:
stripped = message.rstrip()
if stripped:
    session_log.write(stripped)
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest clio/tests/test_log.py -q`  
Expected: PASS (includes `test_print_style_split_write_skips_blank_session_log`)

- [ ] **Step 3: Commit**

```bash
git add clio/log.py clio/tests/test_log.py
git commit -m "fix(log): skip blank session_log rows from print split writes"
```

---

### Task 1: Export `day` + run `day_label` basename

**Files:**
- Modify: `clio/ui/routes/export.py`
- Modify: `clio/ui/routes/run.py` (`handle_post_run_start`, and preview/rerun if they use `day_label` the same way)
- Modify: `clio/tests/test_export_routes.py`
- Modify: `clio/tests/test_routes_run.py`

**Interfaces:**
- Consumes: `clio.ui.services.file_service._is_safe_basename(name: str) -> bool`
- Produces: 400 `{"ok": False, "error": "invalid day"}` / `"invalid day_label"` before any path join

- [ ] **Step 1: Write failing tests**

In `test_export_routes.py`:

```python
def test_unsafe_day_rejected(self, handler: MagicMock) -> None:
    handle_post_export(handler, {}, {"day": "../evil", "format": "jianying"})
    args = handler._send_json.call_args[0]
    assert args[1] == 400
    assert "day" in args[0]["error"].lower() or "invalid" in args[0]["error"].lower()

def test_day_with_slash_rejected(self, handler: MagicMock) -> None:
    handle_post_export(handler, {}, {"day": "a/b", "format": "jianying"})
    assert handler._send_json.call_args[0][1] == 400
```

In `test_routes_run.py` (use existing `_handler` + `_no_thread` fixtures; mock `_get_config` with a minimal config):

```python
def test_unsafe_day_label_rejected(self, tmp_path, _handler, _no_thread):
    handler = _handler
    handler._resolve_project_dir.return_value = tmp_path
    cfg = MagicMock()
    cfg.paths.output_dir = tmp_path / "out"
    cfg.paths.output_dir.mkdir()
    cfg.plan.use_transcripts = True
    handler._get_config.return_value = cfg
    handle_post_run_start(handler, {}, {"day_label": "../x", "steps": ["plan"]})
    assert handler._send_json.call_args[0][1] == 400
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest clio/tests/test_export_routes.py::TestHandlePostExport::test_unsafe_day_rejected clio/tests/test_routes_run.py -k day_label -q`  
Expected: FAIL (unsafe day currently proceeds to 404/start)

- [ ] **Step 3: Implement**

`export.py` after reading `day`:

```python
from clio.ui.services.file_service import _is_safe_basename

day = obj.get("day", "day1")
if not isinstance(day, str) or not _is_safe_basename(day):
    handler._send_json({"ok": False, "error": "invalid day"}, 400)
    return
```

`run.py` in `handle_post_run_start` (and any sibling that takes `day_label` into plan paths):

```python
from clio.ui.services.file_service import _is_safe_basename

day_label = obj.get("day_label", "day1")
if not isinstance(day_label, str) or not _is_safe_basename(day_label):
    return handler._send_json({"ok": False, "error": "invalid day_label"}, 400)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest clio/tests/test_export_routes.py clio/tests/test_routes_run.py -q`

- [ ] **Step 5: Commit**

```bash
git add clio/ui/routes/export.py clio/ui/routes/run.py clio/tests/test_export_routes.py clio/tests/test_routes_run.py
git commit -m "fix(ui): basename-sanitize export day and run day_label"
```

---

### Task 2: Run start deepcopy before body mutation

**Files:**
- Modify: `clio/ui/routes/run.py` (`handle_post_run_start` ~154–167)
- Modify: `clio/tests/test_routes_run.py`

**Interfaces:**
- Produces: body field writes never mutate object returned by `_get_config` cache

- [ ] **Step 1: Write failing test**

```python
def test_use_transcripts_does_not_mutate_cached_config(self, tmp_path, _handler, _no_thread):
    handler = _handler
    handler._resolve_project_dir.return_value = tmp_path
    cfg = MagicMock()
    cfg.paths.output_dir = tmp_path / "out"
    cfg.paths.output_dir.mkdir()
    cfg.plan.use_transcripts = True  # default on shared object
    handler._get_config.return_value = cfg

    handle_post_run_start(handler, {}, {"day_label": "day1", "steps": ["plan"], "use_transcripts": False})
    # Shared cfg must remain default True if handler deepcopied before assign
    assert cfg.plan.use_transcripts is True
```

- [ ] **Step 2: Run — expect FAIL** (today mutates in place → `False`)

- [ ] **Step 3: Implement**

After successful project_dir override (or immediately after `_get_config`), before `use_transcripts` assignment:

```python
import copy
# Always isolate run-local config from cache
if cfg is handler._get_config(proj_dir):  # fragile — better:
cfg = copy.deepcopy(cfg)
# re-apply: override path already deepcopies when project_dir set;
# simplest: always deepcopy once after override returns:
cfg, cfg_error = _apply_run_project_dir_override(...)
if cfg_error: ...
cfg = copy.deepcopy(cfg)  # if override already deepcopied, second copy is OK
if "use_transcripts" in obj:
    cfg.plan.use_transcripts = obj["use_transcripts"]
```

Prefer: change `_apply_run_project_dir_override` to always return a deepcopy even when raw is None:

```python
def _apply_run_project_dir_override(cfg, project_dir_raw):
    if project_dir_raw is None or (isinstance(project_dir_raw, str) and not project_dir_raw.strip()):
        return copy.deepcopy(cfg), None
    ...
```

And still deepcopy when applying `use_transcripts` if override path not taken — **one** guaranteed deepcopy on start is enough:

```python
cfg = copy.deepcopy(handler._get_config(proj_dir))
cfg, cfg_error = _apply_run_project_dir_override(cfg, ...)
```

Note: if override deepcopies again, fine.

- [ ] **Step 4: Run tests PASS + commit**

```bash
git add clio/ui/routes/run.py clio/tests/test_routes_run.py
git commit -m "fix(run): deepcopy config before body field mutation"
```

---

### Task 3: R-033a — sandbox project_dir + cut output_dir

**Files:**
- Modify: `clio/ui/services/project_service.py` — extract allowlist + `is_allowed_project_dir`
- Modify: `clio/ui/routes/run.py` — use allowlist in `_apply_run_project_dir_override`
- Modify: `clio/tasks/cut.py` — `resolve_cut_output_dir` raises or returns error if outside output root
- Modify: `clio/ui/routes/plan.py` — catch and 400
- Modify: `clio/tests/test_routes_run.py`, `clio/tests/test_tasks_cut.py`, `clio/tests/test_routes_plan.py` as needed
- Modify: `clio/tests/test_project_service.py` if present

**Interfaces:**
- Produces:
  - `allowed_project_paths(config_path: Path | None, default_input: Path) -> set[str]`
  - `is_allowed_project_dir(candidate: Path, allowed: set[str]) -> bool`
  - `is_under_root(path: Path, root: Path) -> bool`
  - `resolve_cut_output_dir(...)` — raises `ValueError("output_dir outside project output")` when out of tree

- [ ] **Step 1: Unit tests for helpers (TDD)**

```python
# test_project_service.py or test_routes_run.py
def test_outside_registry_project_dir_rejected(tmp_path):
    cfg = SimpleNamespace(_project_dir=None)
    # allowed only tmp_path / "proj"
    # body path tmp_path / "other" -> error string containing "not allowed"
```

```python
# test_tasks_cut.py
def test_resolve_cut_output_dir_rejects_outside(tmp_path):
    config = SimpleNamespace(paths=SimpleNamespace(output_dir=tmp_path / "out"))
    (tmp_path / "out").mkdir()
    with pytest.raises(ValueError, match="output_dir"):
        resolve_cut_output_dir(config, "day1", tmp_path / "elsewhere")
```

- [ ] **Step 2: Implement helpers**

In `project_service.py` (factor from `resolve_project_input`):

```python
def collect_allowed_project_paths(default_input: Path, config_path: Path | None) -> set[str]:
    allowed = {str(default_input.resolve())}
    registry_file = _registry_path(config_path)
    if registry_file.is_file():
        ...  # same loop as resolve_project_input
    return allowed

def is_under_root(path: Path, root: Path) -> bool:
    try:
        path = path.resolve()
        root = root.resolve()
        return path == root or root in path.parents  # or path.is_relative_to(root) on 3.11+
    except OSError:
        return False
```

Use `path.is_relative_to(root)` (Python 3.11+ project target).

`_apply_run_project_dir_override`: after `is_dir()`, check membership in allowlist. Needs `config_path` + default project root — pass from handler:

```python
# run.py
default_root = handler._resolve_project_dir(qs)  # already
allowed = collect_allowed_project_paths(default_root, handler.config_path)
...
if str(project_dir.resolve()) not in allowed:
    return cfg, f"project_dir not allowed: {project_dir_raw}"
```

**CLI note:** `resolve_cut_output_dir` used from CLI too — enforce under `config.paths.output_dir` always (spec: relative to project output).

```python
def resolve_cut_output_dir(config, day_label, output_dir=None) -> Path:
    root = Path(config.paths.output_dir).expanduser().resolve()
    if output_dir is not None:
        out = Path(output_dir).expanduser().resolve()
        if not out.is_relative_to(root):
            raise ValueError(f"output_dir outside project output: {out}")
        return out
    return (root / "cuts" / day_label).resolve()
```

`plan.py` handle_post_cut:

```python
try:
    actual_out_path = resolve_cut_output_dir(cfg, day_label, out_path)
except ValueError as e:
    return handler._send_json({"ok": False, "error": str(e)}, 400)
```

- [ ] **Step 3: Run related tests PASS**

Run: `python -m pytest clio/tests/test_routes_run.py clio/tests/test_tasks_cut.py clio/tests/test_routes_plan.py clio/tests/test_project_service.py -q`

- [ ] **Step 4: Commit**

```bash
git commit -m "fix(ui): sandbox cut output_dir and run project_dir"
```

---

### Task 4: R-033d — body size cap + constant-time token

**Files:**
- Modify: `clio/ui/server.py` (`_require_auth`, `do_PUT`, `do_POST`)
- Modify: `clio/tests/test_server.py`

**Interfaces:**
- Produces: `MAX_JSON_BODY_BYTES = 8 * 1024 * 1024`
- Auth: equal-length `hmac.compare_digest` only

- [ ] **Step 1: Failing tests**

```python
def test_post_body_over_limit_returns_413(self, ...):
    # build handler with Content-Length = MAX+1; assert 413; rfile.read not called with huge length
```

```python
def test_auth_uses_compare_digest(monkeypatch):
    # optional: patch hmac.compare_digest and assert called when lengths match
```

If integration-style tests are heavy, unit-test a extracted helper:

```python
def _parse_content_length(headers, max_bytes=MAX_JSON_BODY_BYTES) -> tuple[int | None, int | None]:
    """Returns (length, error_status). error_status 400/413 or None."""
```

- [ ] **Step 2: Implement body cap**

Near top of `server.py` or inside `make_handler`:

```python
import hmac
MAX_JSON_BODY_BYTES = 8 * 1024 * 1024

def _read_json_body(self) -> tuple[dict | None, int | None]:
    raw_len = self.headers.get("Content-Length", "0")
    try:
        length = int(raw_len)
    except (TypeError, ValueError):
        return None, 400
    if length < 0:
        return None, 400
    if length > MAX_JSON_BODY_BYTES:
        return None, 413
    raw = self.rfile.read(length) if length else b""
    try:
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("expected a JSON object")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None, 400
    return obj, None
```

Use in `do_PUT` / `do_POST`. On 413: `_send_json({"ok": False, "error": "request body too large"}, 413)`.

- [ ] **Step 3: Implement auth**

```python
def _require_auth(self) -> bool:
    token = self.__class__._api_token
    if not token:
        return True
    auth = self.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        provided = auth[7:]
        if isinstance(provided, str) and len(provided) == len(token) and hmac.compare_digest(provided, token):
            return True
    url = urlparse(self.path)
    qs = parse_qs(url.query)
    provided = qs.get("token", [None])[0]
    if isinstance(provided, str) and len(provided) == len(token) and hmac.compare_digest(provided, token):
        return True
    self._send_json({"error": "未授权访问，需要有效的 API Token"}, 401)
    return False
```

- [ ] **Step 4: Tests PASS + commit**

```bash
git commit -m "fix(ui): cap JSON body size and constant-time token compare"
```

---

### Task 5: R-033b — strip/mask api_key + env-only errors

**Files:**
- Modify: `clio/ui/routes/config_routes.py` — `_normalize_provider`, GET handlers, POST/PUT provider responses
- Modify: `clio/ai/gemini.py`, `clio/doctor.py`, `clio/main.py` — error strings
- Modify: `clio/tests/test_routes_config.py` (and doctor/gemini tests if they assert old copy)
- **Do not change** `_resolve_api_key` env-first yaml-fallback behavior

**Interfaces:**
- Produces: `_mask_provider_dict(d: dict) -> dict` deep-copies and sets non-empty `api_key` to `"********"`

- [ ] **Step 1: Tests**

```python
def test_normalize_provider_strips_api_key():
    p = _normalize_provider("g", {"type": "gemini", "api_key": "SECRET", "api_key_env": "GEMINI_API_KEY"})
    assert p.get("api_key") in ("", None) or p["api_key"] == ""

def test_get_providers_masks_key(tmp_path, ...):
    # write yaml with api_key: sk-test → GET returns ********
```

- [ ] **Step 2: Implement**

```python
def _normalize_provider(name: str, obj: dict[str, Any]) -> dict[str, Any]:
    data = {
        ...
        "api_key": "",  # never persist
        "api_key_env": obj.get("api_key_env", ""),
        ...
    }
```

```python
def _mask_secrets_in_raw(raw: dict) -> dict:
    import copy
    out = copy.deepcopy(raw)
    providers = out.get("ai", {}).get("providers", {})
    for p in providers.values():
        if isinstance(p, dict) and p.get("api_key"):
            p["api_key"] = "********"
    return out
```

Apply mask in `handle_get_providers`, `handle_get_config_raw` / global raw GET, and provider POST/PUT response `provider` field.

Error copy example (`gemini.py` / doctor): replace “config.yaml api_key” with “set GEMINI_API_KEY in `.env` or environment”.

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(config): strip yaml api_key on write and mask on GET"
```

---

### Task 6: R-033c — `validate_global_config`

**Files:**
- Modify: `clio/config/validators.py`
- Modify: `clio/config/loader.py` (`load_global_config` end)
- Modify: `clio/config/__init__.py` exports if needed
- Modify: `clio/tests/test_config.py` / `test_config_v2.py`

**Interfaces:**
- Produces: `validate_global_config(config: GlobalConfig) -> None` raises `ValueError`

- [ ] **Step 1: Failing tests**

```python
def test_validate_global_rejects_bad_provider_type():
    gc = GlobalConfig(ai=GlobalAIConfig(providers={"x": ProviderConfig(name="x", type="nope")}))
    with pytest.raises(ValueError, match="type"):
        validate_global_config(gc)

def test_validate_global_allows_zero_timeout():
    # timeout_sec=0 must NOT raise
    validate_global_config(...)
```

- [ ] **Step 2: Implement**

```python
def validate_global_config(config: GlobalConfig) -> None:
    if config.proxy.enabled and not config.proxy.url:
        raise ValueError("proxy.enabled=true 但 proxy.url 为空。...")
    _require_min("ai.provider_ttl_min", config.ai.provider_ttl_min, 0)
    _require_min("naming.index_width", config.naming.index_width, 1)
    for provider_name, provider_cfg in config.ai.providers.items():
        _require_supported_provider_type(provider_name, provider_cfg.type)
        _require_min(f"ai.providers.{provider_name}.requests_per_minute", provider_cfg.requests_per_minute, 0)
        _require_min(f"ai.providers.{provider_name}.retry_attempts", provider_cfg.retry_attempts, 0)
        _require_min(f"ai.providers.{provider_name}.max_tokens", provider_cfg.max_tokens, 0)
        _require_min(f"ai.providers.{provider_name}.timeout_sec", provider_cfg.timeout_sec, 0)
        _require_min(f"ai.providers.{provider_name}.poll_interval_sec", provider_cfg.poll_interval_sec, 0)
```

Call at end of `load_global_config` before return. Global PUT already loads via `load_global_config(tmp)` → covered.

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(config): validate global config on load and PUT"
```

---

### Task 7: R-033e — `_matches_selected_*` tests only

**Files:**
- Modify: `clio/tests/test_helpers.py` (import matchers)
- No production change unless a bug is proven

**Interfaces:**
- Consumes: `_matches_selected_artifact(path: Path, selected: set[str]) -> bool`

- [ ] **Step 1: Add tests**

```python
import json
from clio.tasks._helpers import _matches_selected_artifact, _matches_selected_stem

def test_matches_media_identity_stems(tmp_path: Path):
    p = tmp_path / "unrelated_name.json"
    p.write_text(json.dumps({
        "media_identity": {
            "compressed_stem": "001_GL010684",
            "original_stem": "GL010684",
        }
    }), encoding="utf-8")
    assert _matches_selected_artifact(p, {"001_GL010684"}) is True
    assert _matches_selected_artifact(p, {"GL010684"}) is True
    assert _matches_selected_artifact(p, {"other"}) is False

def test_matches_source_file_only(tmp_path: Path):
    p = tmp_path / "001_街头风景.json"
    p.write_text(json.dumps({"source_file": "GL010684.MP4"}), encoding="utf-8")
    assert _matches_selected_artifact(p, {"GL010684"}) is True

def test_corrupt_json_false(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    assert _matches_selected_artifact(p, {"x"}) is False

def test_stem_direct_match(tmp_path: Path):
    p = tmp_path / "001_foo.json"
    p.write_text("{}", encoding="utf-8")
    assert _matches_selected_stem(p, {"001_foo"}) is True
```

Add `index` int/padded case documenting current behavior (assert actual result).

- [ ] **Step 2: Run PASS + commit**

```bash
git commit -m "test(helpers): cover _matches_selected_* identity-only JSON"
```

---

### Task 8: I1 — Plan respects `files=`

**Files:**
- Modify: `clio/tasks/plan.py`
- Modify: `clio/tests/test_plan.py` and/or `test_tasks_*` plan tests

**Interfaces:**
- Consumes: `_selected_stems`, `_matches_selected_artifact` from `clio.tasks._helpers`

- [ ] **Step 1: Failing test**

Create two analysis JSON files; call `run_plan_vlog` with `files=[stem_of_one]` and mock `plan_daily_vlog` to capture `clips` length / indices.

```python
def test_plan_filters_by_files(tmp_path, monkeypatch):
    # setup texts_dir with a.json and b.json identities
    captured = {}
    def fake_plan(clips, *a, **k):
        captured["n"] = len(clips)
        return {"sequence": [], "day_title": "t", "total_estimated_sec": 0}
    monkeypatch.setattr("clio.tasks.plan.plan_daily_vlog", fake_plan)
    run_plan_vlog(config, files=["only_a_stem"], overwrite=True)
    assert captured["n"] == 1
```

- [ ] **Step 2: Implement**

```python
from clio.tasks._helpers import _matches_selected_artifact, _selected_stems

selected = _selected_stems(files) if files is not None else None
...
for json_file in sorted(config.texts_dir.glob("*.json")):
    if selected is not None and not _matches_selected_artifact(json_file, selected):
        continue
    ...
if not clips:
    print("[规划] 无可用素材（选片过滤后为空）")
    return None
```

Remove the “使用所有素材…筛选仅影响前序” message; log filtered count when `files is not None`.

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(plan): honor files= selection when building clips"
```

---

### Task 9: I3 — Label ProcessingState key

**Files:**
- Modify: `clio/tasks/label.py` (~120)
- Modify: `clio/tests/test_tasks_label.py`

- [ ] **Step 1: Test** that `state.mark` receives source stem when file is `001_AITitle.json` with `"source_file": "GL01.MP4"`.

- [ ] **Step 2: Implement** (after loading `data` from json_file — load early if not already):

```python
data = json.loads(json_file.read_text(encoding="utf-8"))
orig_stem = Path(data.get("source_file") or data.get("compressed_file") or json_file.stem).stem
```

Align with `scripts.py:41`. Prefer identity stems if `load_identity(data)` available and cheap.

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(label): key ProcessingState by source/compressed stem"
```

---

### Task 10: I4 — Serial voiceover try/except

**Files:**
- Modify: `clio/tasks/scripts.py` serial branch (~108–132)
- Modify: `clio/tests/test_tasks_scripts.py`

- [ ] **Step 1: Test** — mock `_process_one_script` to raise on file 2; assert file 3 still called when `max_workers=1`.

- [ ] **Step 2: Implement**

```python
error_count = 0
for json_file in input_files:
    if cancel_event and cancel_event.is_set():
        ...
        break
    try:
        result = _process_one_script(...)
        if result == "cancelled":
            break
        if result is True:
            print(f"  ✓ ...")
        elif isinstance(result, str):
            print(f"  [错误] {json_file.stem}: {result}")
            error_count += 1
    except Exception as e:
        print(f"  [错误] {json_file.stem}: {e}")
        error_count += 1
if error_count:
    print(f"  [警告] {error_count} 个 voiceover 生成失败")
```

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(scripts): continue serial voiceover after per-file errors"
```

---

### Task 11: I7 — Refine return completed count

**Files:**
- Modify: `clio/tasks/refine.py` (`return completed` at both exit points)
- Modify: `clio/tests/test_tasks_refine.py`

- [ ] **Step 1: Test** partial failures → return value equals success count.

- [ ] **Step 2: Change**

```python
return completed  # was: return len(target_files)
```

in both `run_refine_texts` and `run_refine_scripts`. Grep callers; CLI ignores return — OK.

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(refine): return success count instead of target count"
```

---

### Task 12: I8 — Progress ETA phase reset

**Files:**
- Modify: `clio/progress.py` (`update` when phase changes)
- Modify: `clio/tests/test_progress.py`

- [ ] **Step 1: Test**

```python
def test_phase_change_resets_eta_clock(tmp_path):
    times = iter([100.0, 100.0, 110.0, 110.0, 112.0, 112.0])
    with mock.patch("clio.progress.time.monotonic", side_effect=lambda: next(times)):
        t = ProgressTracker(tmp_path)
        t.update(phase="a", total=10, current=5)  # uses elapsed from 100
        t.update(phase="b", total=10)  # reset start
        t.update(current=2)  # elapsed should be ~2s from new start, not 12
        data = json.loads(t._path.read_text(encoding="utf-8"))
        # rate = 2/2 = 1 → remaining 8 → eta_sec == 8
        assert data["eta_sec"] == 8
```

Adjust side_effect length carefully to match call order (`__init__` also calls monotonic).

- [ ] **Step 2: Implement**

```python
if phase is not None:
    if phase != self._data["phase"]:
        self._start = time.monotonic()
        self._data["eta_sec"] = None
    self._data["phase"] = phase
    self._data["current"] = 0
```

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(progress): reset ETA clock when phase changes"
```

---

### Task 13: Wave6a — Cancel partial file cleanup

**Files:**
- Modify: `clio/tasks/cut.py` (`replace_file_safely`)
- Modify: `clio/tasks/compress.py` and/or `clio/compress.py`
- Modify: `clio/tests/test_tasks_cut.py`, `clio/tests/test_tasks_compress.py` / `test_compress.py`

- [ ] **Step 1: Tests**

```python
def test_replace_file_safely_unlinks_partial_without_bak(tmp_path):
    dest = tmp_path / "out.mp4"
    def boom(p):
        p.write_bytes(b"partial")
        raise InterruptedError("cancel")
    with pytest.raises(InterruptedError):
        replace_file_safely(dest, boom)
    assert not dest.exists()
```

Compress: after cancel mock, output path missing.

- [ ] **Step 2: Implement cut**

```python
except Exception:
    if bak is not None and bak.exists():
        ...  # existing restore
    elif dest.exists():
        dest.unlink(missing_ok=True)
    raise
```

Compress task loop:

```python
try:
    compress_video(..., cancel_event=cancel_event)
except BaseException:
    if use_out.exists():
        # only if this attempt created/truncated — if skip path never opened, OK
        use_out.unlink(missing_ok=True)
    raise
```

Be careful not to delete pre-existing good file when overwrite=False skip path — only unlink when this invocation was writing `use_out`.

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(media): remove partial cut/compress outputs on cancel"
```

---

### Task 14: Wave6b — Waveform abspath = video gate

**Files:**
- Modify: `clio/ui/routes/waveform.py` (`_original_allowed`)
- Optional: extract shared helper with `videos.py` into `file_service` or small module
- Modify: `clio/tests/test_routes_waveform.py`

- [ ] **Step 1: Tests** — empty selection + abspath → not allowed; exact selected path → allowed; same basename different dir → denied.

- [ ] **Step 2: Implement**

```python
def _original_allowed(proj_dir: Path, vp: Path) -> bool:
    selected = load_selected_videos(proj_dir)
    if not selected:
        return False
    allowed: set[Path] = set()
    for p in selected:
        try:
            allowed.add(p.resolve())
        except OSError:
            allowed.add(p)
    return vp in allowed  # no basename fallback
```

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(waveform): require exact selected path for abspath"
```

---

### Task 15: ROADMAP + full verification

**Files:**
- Modify: `ROADMAP.md` — R-033a–e done; note pipeline I1/I3/I4/I7/I8 + export day + run deepcopy + Wave6 under recently completed / residual

- [ ] **Step 1: Full test suite**

```bash
python -m pytest clio/tests/ -q --tb=line
npm test -- --run
```

Expected: all green (or document any pre-existing unrelated fail).

- [ ] **Step 2: Update ROADMAP** phases R-033a–e to **Done** with date 2026-07-23; list residuals from design § Residual.

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: mark R-033 hardening and pipeline robustness done"
```

---

## Self-review (plan vs spec)

| Spec item | Task |
| --- | --- |
| Wave0 log blank | Task 0 |
| Export day + run day_label | Task 1 |
| Run deepcopy | Task 2 |
| R-033a sandbox | Task 3 |
| R-033d body + compare_digest | Task 4 |
| R-033b api_key | Task 5 |
| R-033c validate_global | Task 6 |
| R-033e tests | Task 7 |
| I1/I3/I4/I7/I8 | Tasks 8–12 |
| Wave6a/b | Tasks 13–14 |
| ROADMAP | Task 15 |
| Non-goals | Global constraints — not tasked |

**Placeholder scan:** No TBD/TODO left in steps.  
**Type consistency:** `is_under_root` / `collect_allowed_project_paths` / `_mask_secrets_in_raw` / `validate_global_config` names stable across tasks.

**Execution note:** Tasks 0–2 are independent quick wins; 3 depends on project_service; 5–6 both touch config — keep separate commits; 8–12 independent pipeline tasks can run in any order after 0–7.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-07-23-r033-hardening-and-pipeline-robustness-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans checkpoints  

Which approach?
