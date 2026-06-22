# R-014 Token Usage Statistics — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track AI token usage per-project: provider returns `AIResponse` with token counts, `FileTokenUsageStore` persists to `.token_usage.json`, UI displays stats.

**Architecture:** `TokenUsage` + `AIResponse` dataclasses → providers return enriched responses → `_call_ai()` collects into `TokenUsageStore` → backend route serves aggregated stats → UI sidebar entity + CLI command.

**Tech Stack:** Python 3.11+, existing google-genai / httpx providers, stdlib http.server frontend

---

### Task 1: Foundation Types + Store

**Files:**
- Modify: `vlog_tool/ai/base.py` (add TokenUsage, AIResponse, update Protocol)
- Create: `vlog_tool/ai/token_usage.py` (TokenUsageStore ABC + FileTokenUsageStore)

- [ ] **Step 1.1: Add TokenUsage and AIResponse to base.py**

Add after `TaskName` enum:

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AIResponse:
    text: str
    token_usage: TokenUsage | None = None
```

Change `TextAIProvider.generate_text` return type from `str` to `AIResponse`:

```python
class TextAIProvider(Protocol):
    provider_id: str
    def generate_text(self, prompt: str, model: str) -> AIResponse: ...
    def close(self) -> None: ...
```

Change `VideoAIProvider.analyze_video` return type:

```python
class VideoAIProvider(TextAIProvider, Protocol):
    def analyze_video(
        self, video_path: str, prompt: str, model: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AIResponse: ...
```

- [ ] **Step 1.2: Create token_usage.py**

```python
"""Token usage tracking — records AI token consumption per project."""
from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from vlog_tool.utils import write_json_atomic

if TYPE_CHECKING:
    from vlog_tool.ai.base import TokenUsage


class TokenUsageStore(ABC):
    @abstractmethod
    def record(self, task: str, model: str, usage: TokenUsage) -> None: ...
    @abstractmethod
    def get_stats(self) -> dict: ...
    def close(self) -> None: ...


_EMPTY_STATS: dict = {
    "total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    "by_model": {},
    "by_task": {},
    "history": [],
}


def _merge_stats(stats: dict, task: str, model: str, pt: int, ct: int, tt: int) -> dict:
    stats["total"]["prompt_tokens"] += pt
    stats["total"]["completion_tokens"] += ct
    stats["total"]["total_tokens"] += tt

    model_key = stats["by_model"].setdefault(model, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0})
    model_key["prompt_tokens"] += pt
    model_key["completion_tokens"] += ct
    model_key["total_tokens"] += tt
    model_key["calls"] += 1

    task_key = stats["by_task"].setdefault(task, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0})
    task_key["prompt_tokens"] += pt
    task_key["completion_tokens"] += ct
    task_key["total_tokens"] += tt
    task_key["calls"] += 1

    return stats


class FileTokenUsageStore(TokenUsageStore):
    def __init__(self, output_dir: str):
        self._path = Path(output_dir) / ".token_usage.json"
        self._lock = threading.Lock()

    def record(self, task: str, model: str, usage: TokenUsage) -> None:
        with self._lock:
            raw = self._read_raw()
            entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "task": task,
                "model": model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
            raw["history"].append(entry)
            _merge_stats(raw, task, model, usage.prompt_tokens, usage.completion_tokens, usage.total_tokens)
            write_json_atomic(self._path, raw)

    def get_stats(self) -> dict:
        return self._read_raw()

    def close(self) -> None:
        pass

    def _read_raw(self) -> dict:
        if not self._path.is_file():
            return {"total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "by_model": {}, "by_task": {}, "history": []}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "by_model": {}, "by_task": {}, "history": []}
```

- [ ] **Step 1.3: Verify no syntax errors**

```bash
.\.venv\Scripts\python.exe -c "from vlog_tool.ai.base import TokenUsage, AIResponse, TextAIProvider, VideoAIProvider, TaskName; print('OK')"
.\.venv\Scripts\python.exe -c "from vlog_tool.ai.token_usage import TokenUsageStore, FileTokenUsageStore; print('OK')"
```

Expected: `OK` for both.

- [ ] **Step 1.4: Commit**

```bash
git add vlog_tool/ai/base.py vlog_tool/ai/token_usage.py
git commit -m "feat(ai): add TokenUsage, AIResponse types and FileTokenUsageStore"
```

---

### Task 2: Update Gemini Provider

**Files:**
- Modify: `vlog_tool/ai/gemini.py`

- [ ] **Step 2.1: Update import + generate_text to return AIResponse**

At top, add import:
```python
from vlog_tool.ai.base import AIResponse, TokenUsage
```

Change `generate_text`:

```python
def generate_text(self, prompt: str, model: str) -> AIResponse:
    def _do() -> AIResponse:
        self._maybe_wait()
        response = self._client.models.generate_content(model=model, contents=prompt)
        usage = None
        if response.usage_metadata:
            meta = response.usage_metadata
            usage = TokenUsage(
                prompt_tokens=meta.prompt_token_count or 0,
                completion_tokens=meta.candidates_token_count or 0,
                total_tokens=meta.total_token_count or 0,
            )
        return AIResponse(text=response.text or "", token_usage=usage)
    return self._call_with_retry(_do, model, model)
```

Change `analyze_video`:

```python
def analyze_video(
    self, video_path: str, prompt: str, model: str, progress_callback: Callable[[str], None] | None = None
) -> AIResponse:
    uploaded = None
    try:
        ...
        def _do() -> AIResponse:
            self._maybe_wait()
            response = self._client.models.generate_content(
                model=model,
                contents=[uploaded, prompt],
            )
            usage = None
            if response.usage_metadata:
                meta = response.usage_metadata
                usage = TokenUsage(
                    prompt_tokens=meta.prompt_token_count or 0,
                    completion_tokens=meta.candidates_token_count or 0,
                    total_tokens=meta.total_token_count or 0,
                )
            return AIResponse(text=response.text or "", token_usage=usage)
        return self._call_with_retry(_do, f"视频 {model}", model)
    finally:
        ...
```

- [ ] **Step 2.2: Verify**

```bash
.\.venv\Scripts\python.exe -c "from vlog_tool.ai.gemini import GeminiProvider; print('OK')"
```

- [ ] **Step 2.3: Commit**

```bash
git add vlog_tool/ai/gemini.py
git commit -m "feat(ai): Gemini provider returns AIResponse with token_usage"
```

---

### Task 3: Update OpenAI Compat Provider

**Files:**
- Modify: `vlog_tool/ai/openai_compat.py`

- [ ] **Step 3.1: Update import + generate_text**

At top, add import:
```python
from vlog_tool.ai.base import AIResponse, TokenUsage
```

Change `generate_text`:

```python
def generate_text(self, prompt: str, model: str) -> AIResponse:
    def _do() -> AIResponse:
        self._maybe_wait()
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self._max_tokens,
                "temperature": 0.3,
            },
        )
        sc = response.status_code
        if sc == 429 or sc >= 500:
            raise httpx.HTTPStatusError(f"status {sc}", request=response.request, response=response)
        if 400 <= sc < 500:
            body = response.text[:200]
            raise ValueError(f"API {self._base_url} 返回 {sc}: {body}")
        data = response.json()
        usage_raw = data.get("usage")
        usage = None
        if usage_raw:
            usage = TokenUsage(
                prompt_tokens=usage_raw.get("prompt_tokens", 0),
                completion_tokens=usage_raw.get("completion_tokens", 0),
                total_tokens=usage_raw.get("total_tokens", 0),
            )
        return AIResponse(
            text=data["choices"][0]["message"]["content"],
            token_usage=usage,
        )
    return with_retry(
        _do,
        attempts=self._retry_attempts,
        base_delay=1.0,
        retry_on=(httpx.HTTPError,),
        what=f"OpenAI 兼容 {self._base_url}",
    )
```

- [ ] **Step 3.2: Verify**

```bash
.\.venv\Scripts\python.exe -c "from vlog_tool.ai.openai_compat import OpenAICompatProvider; print('OK')"
```

- [ ] **Step 3.3: Commit**

```bash
git add vlog_tool/ai/openai_compat.py
git commit -m "feat(ai): OpenAI compat provider returns AIResponse with token_usage"
```

---

### Task 4: Update analyze.py — Token Collection

**Files:**
- Modify: `vlog_tool/analyze.py`

- [ ] **Step 4.1: Update _call_ai signature and body**

```python
def _call_ai(
    label: str,
    provider_id: str,
    model: str,
    prompt: str,
    fn,
    *,
    debug_print: bool = False,
    token_store=None,
    task_name: str = "",
) -> str:
    if debug_print:
        print("=" * 60)
        print(f"[DEBUG PROMPT] {label} ({provider_id}/{model})")
        print("-" * 60)
        print(prompt)
        print("=" * 60)
    prompt_bytes = len(prompt.encode("utf-8"))
    print(f"  AI: {provider_id}/{model}（prompt {format_size(prompt_bytes)}）")
    with timed(f"{label} {provider_id}/{model}"):
        resp = fn()
    print(f"  响应: {format_size(len(resp.text.encode('utf-8')))}")
    if token_store and resp.token_usage:
        token_store.record(task_name or label, model, resp.token_usage)
    return resp.text
```

- [ ] **Step 4.2: Update all 5 caller functions**

`analyze_video`:
```python
def analyze_video(
    video_path: str, config: AppConfig,
    progress_callback: Callable[[str], None] | None = None,
    token_store=None,
) -> dict:
    provider, model = get_video_provider(config, TaskName.VIDEO_ANALYZE)
    prompt = _wrap_with_context(ANALYZE_PROMPT, config)
    text = _call_ai(
        "AI 视频分析",
        provider.provider_id,
        model,
        prompt,
        lambda: provider.analyze_video(video_path, prompt, model, progress_callback=progress_callback),
        debug_print=config.ai.debug_print_prompt,
        token_store=token_store,
        task_name=TaskName.VIDEO_ANALYZE,
    )
    return _validate_analysis(extract_json(text), video_path)
```

`generate_voiceover`:
```python
def generate_voiceover(clip_data: dict, template: str, config: AppConfig, token_store=None) -> dict:
    ...
    text = _call_ai(
        "AI 口播",
        provider.provider_id,
        model,
        prompt,
        lambda: provider.generate_text(prompt, model),
        debug_print=config.ai.debug_print_prompt,
        token_store=token_store,
        task_name=TaskName.VOICEOVER,
    )
    return _validate_voiceover(extract_json(text), clip_data.get("title", ""))
```

`plan_daily_vlog`:
```python
def plan_daily_vlog(
    clips: list[dict],
    config: AppConfig,
    day_label: str = "day1",
    transcripts_map: dict[str, dict] | None = None,
    use_transcripts: bool = True,
    token_store=None,
) -> dict:
    ...
    text = _call_ai(
        "AI vlog 剪辑规划",
        provider.provider_id,
        model,
        prompt,
        lambda: provider.generate_text(prompt, model),
        debug_print=config.ai.debug_print_prompt,
        token_store=token_store,
        task_name=TaskName.VLOG_PLAN,
    )
    ...
```

`refine_text`:
```python
def refine_text(analysis: dict, config: AppConfig, fix: str | None = None, context_override: str | None = None, token_store=None) -> dict:
    ...
    text = _call_ai(
        label,
        provider.provider_id,
        model,
        prompt,
        lambda: provider.generate_text(prompt, model),
        debug_print=config.ai.debug_print_prompt,
        token_store=token_store,
        task_name=TaskName.REFINE_TEXT,
    )
    ...
```

`refine_script`:
```python
def refine_script(
    script: dict, analysis: dict | None, config: AppConfig,
    fix: str | None = None, context_override: str | None = None,
    token_store=None,
) -> dict:
    ...
    text = _call_ai(
        label,
        provider.provider_id,
        model,
        prompt,
        lambda: provider.generate_text(prompt, model),
        debug_print=config.ai.debug_print_prompt,
        token_store=token_store,
        task_name=TaskName.REFINE_TEXT,
    )
    ...
```

- [ ] **Step 4.3: Verify**

```bash
.\.venv\Scripts\python.exe -c "from vlog_tool.analyze import analyze_video, generate_voiceover, plan_daily_vlog, refine_text, refine_script; print('OK')"
```

- [ ] **Step 4.4: Commit**

```bash
git add vlog_tool/analyze.py
git commit -m "feat(analyze): collect token usage from AIResponse in _call_ai"
```

---

### Task 5: Pipeline Integration (tasks/*.py)

**Files:**
- Modify: `vlog_tool/tasks/analyze.py`
- Modify: `vlog_tool/tasks/scripts.py`
- Modify: `vlog_tool/tasks/refine.py`
- Modify: `vlog_tool/tasks/plan.py`

- [ ] **Step 5.1: Update tasks/analyze.py**

Add import at top:
```python
from vlog_tool.ai.token_usage import FileTokenUsageStore
```

In `run_analyze_all`, add after creating output dir:
```python
token_store = FileTokenUsageStore(str(config.paths.output_dir))
```

Pass to `analyze_video`:
```python
analysis = analyze_video(str(compressed), config, progress_callback=_on_progress, token_store=token_store)
```

- [ ] **Step 5.2: Update tasks/scripts.py**

Add import + create store in `run_generate_scripts`:
```python
from vlog_tool.ai.token_usage import FileTokenUsageStore
...
token_store = FileTokenUsageStore(str(config.paths.output_dir))
```

Pass to `generate_voiceover`:
```python
script = generate_voiceover(data, template, config, token_store=token_store)
```

- [ ] **Step 5.3: Update tasks/refine.py**

Add import, create store in `run_refine_texts` and `run_refine_scripts`:
```python
from vlog_tool.ai.token_usage import FileTokenUsageStore
```

In `run_refine_texts`:
```python
token_store = FileTokenUsageStore(str(config.paths.output_dir))
...
refined = refine_text(analysis, config, fix=fix, context_override=context_override, token_store=token_store)
```

In `run_refine_scripts`:
```python
token_store = FileTokenUsageStore(str(config.paths.output_dir))
...
refined = refine_script(script, analysis, config, fix=fix, context_override=context_override, token_store=token_store)
```

- [ ] **Step 5.4: Update tasks/plan.py**

Add import at top:
```python
from vlog_tool.ai.token_usage import FileTokenUsageStore
```

In `run_plan_vlog`, add after `config.plans_dir.mkdir(...)`:
```python
token_store = FileTokenUsageStore(str(config.paths.output_dir))
```

Pass to `plan_daily_vlog` (add `token_store=token_store`):
```python
plan = plan_daily_vlog(
    clips, config, day_label,
    transcripts_map=transcripts_map,
    use_transcripts=config.plan.use_transcripts,
    token_store=token_store,
)
```

- [ ] **Step 5.5: Verify all task modules import**

```bash
.\.venv\Scripts\python.exe -c "from vlog_tool.tasks.analyze import run_analyze_all; from vlog_tool.tasks.scripts import run_generate_scripts; from vlog_tool.tasks.refine import run_refine_texts, run_refine_scripts; from vlog_tool.tasks.plan import run_plan_vlog; print('OK')"
```

- [ ] **Step 5.6: Commit**

```bash
git add vlog_tool/tasks/analyze.py vlog_tool/tasks/scripts.py vlog_tool/tasks/refine.py vlog_tool/tasks/plan.py
git commit -m "feat(tasks): inject FileTokenUsageStore into all AI pipeline steps"
```

---

### Task 6: Backend API Route

**Files:**
- Create: `vlog_tool/ui/routes/token_routes.py`
- Modify: `vlog_tool/ui/server.py`

- [ ] **Step 6.1: Create token_routes.py**

```python
"""Token usage API routes."""
from __future__ import annotations

from vlog_tool.ai.token_usage import FileTokenUsageStore


def handle_get_token_usage(handler, qs):
    proj_out = handler._project_output_dir(qs)
    if proj_out is None:
        return handler._send_json({"ok": False, "error": "no project"})
    store = FileTokenUsageStore(str(proj_out))
    stats = store.get_stats()
    return handler._send_json(stats)
```

- [ ] **Step 6.2: Register in server.py**

Add import:
```python
from vlog_tool.ui.routes.token_routes import handle_get_token_usage
```

Add route in `do_GET` (between the whisper routes and env/logs):
```python
if path == "/api/token-usage":
    return handle_get_token_usage(self, qs)
```

- [ ] **Step 6.3: Verify**

```bash
.\.venv\Scripts\python.exe -c "from vlog_tool.ui.routes.token_routes import handle_get_token_usage; print('OK')"
```

- [ ] **Step 6.4: Commit**

```bash
git add vlog_tool/ui/routes/token_routes.py vlog_tool/ui/server.py
git commit -m "feat(ui): add GET /api/token-usage backend route"
```

---

### Task 7: CLI Tokens Subcommand

**Files:**
- Modify: `main.py`

- [ ] **Step 7.1: Add tokens subcommand**

After the `serve` subcommand block:

```python
p_tokens = sub.add_parser("tokens", help="查看 token 使用统计")
p_tokens.set_defaults(func=cmd_tokens)
```

Add handler function near the other `cmd_*` functions:

```python
def cmd_tokens(args):
    config = load_config(args)
    from vlog_tool.ai.token_usage import FileTokenUsageStore
    store = FileTokenUsageStore(str(config.paths.output_dir))
    import json
    stats = store.get_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
```

- [ ] **Step 7.2: Verify**

```bash
.\.venv\Scripts\python.exe main.py tokens --help
```

- [ ] **Step 7.3: Commit**

```bash
git add main.py
git commit -m "feat(cli): add tokens subcommand for token usage stats"
```

---

### Task 8: Frontend UI — Sidebar Entity + Token Panel

**Files:**
- Modify: `vlog_tool/ui/static/index.html`
- Modify: `vlog_tool/ui/static/src/sidebar.js`
- Modify: `vlog_tool/ui/static/src/editor.js`
- Modify: `vlog_tool/ui/static/src/utils.js`
- Modify: `vlog_tool/ui/static/src/main.js`
- Modify: `vlog_tool/ui/static/style.css`

- [ ] **Step 8.1: Add sidebar item in index.html**

After the "日志" `<li>` (line 54), add:

```html
<li class="project-item" data-entity="tokens" title="查看 AI token 使用统计">
  <span class="icon"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg></span>
  <span class="name">Tokens</span>
</li>
```

Add tab-pane after `#tab-logs`:

```html
<div id="tab-tokens" class="tab-pane"></div>
```

- [ ] **Step 8.2: Add selectTokens() in sidebar.js**

In `sidebar.js`, add after `selectLogs`:

```js
async function selectTokens() {
  state.currentEntity = 'tokens';
  markDirty(false);
  const { renderActiveTab } = await import('./editor.js');
  renderActiveTab();
}
```

Add to exports:
```js
selectTokens,
```

- [ ] **Step 8.3: Add renderActiveTab branch in editor.js**

In `renderActiveTab()`, after the `logs` branch:
```js
if (state.currentEntity === 'tokens') {
  renderTokens();
  return;
}
```

Add the `renderTokens` function:
```js
async function renderTokens() {
  const pane = $('tab-tokens');
  pane.innerHTML = '<p class="muted">加载中...</p>';
  try {
    const data = await api('GET', '/api/token-usage');
    if (!data || !data.total) {
      pane.innerHTML = '<p class="muted">暂无 token 使用数据。运行流水线后会自动记录。</p>';
      return;
    }
    const t = data.total;
    const totalHtml = `
      <div style="display:flex;gap:var(--space-3);margin-bottom:var(--space-3);flex-wrap:wrap">
        <div class="token-card"><div class="token-card-value">${t.total_tokens.toLocaleString()}</div><div class="token-card-label">总 Token</div></div>
        <div class="token-card"><div class="token-card-value">${t.prompt_tokens.toLocaleString()}</div><div class="token-card-label">Prompt</div></div>
        <div class="token-card"><div class="token-card-value">${t.completion_tokens.toLocaleString()}</div><div class="token-card-label">Completion</div></div>
      </div>`;

    let modelHtml = '<h4 style="margin:var(--space-2) 0">按模型</h4><table class="token-table"><tr><th>模型</th><th>调用次数</th><th>Prompt</th><th>Completion</th><th>总计</th></tr>';
    for (const [model, m] of Object.entries(data.by_model || {})) {
      modelHtml += `<tr><td>${escapeHtml(model)}</td><td>${m.calls}</td><td>${m.prompt_tokens.toLocaleString()}</td><td>${m.completion_tokens.toLocaleString()}</td><td>${m.total_tokens.toLocaleString()}</td></tr>`;
    }
    modelHtml += '</table>';

    let taskHtml = '<h4 style="margin:var(--space-2) 0">按任务</h4><table class="token-table"><tr><th>任务</th><th>调用次数</th><th>Prompt</th><th>Completion</th><th>总计</th></tr>';
    for (const [task, tk] of Object.entries(data.by_task || {})) {
      taskHtml += `<tr><td>${escapeHtml(task)}</td><td>${tk.calls}</td><td>${tk.prompt_tokens.toLocaleString()}</td><td>${tk.completion_tokens.toLocaleString()}</td><td>${tk.total_tokens.toLocaleString()}</td></tr>`;
    }
    taskHtml += '</table>';

    let historyHtml = '<h4 style="margin:var(--space-2) 0">历史记录</h4><table class="token-table"><tr><th>时间</th><th>任务</th><th>模型</th><th>Prompt</th><th>Completion</th><th>总计</th></tr>';
    for (const h of (data.history || []).slice().reverse().slice(0, 100)) {
      historyHtml += `<tr><td class="token-time">${escapeHtml(h.timestamp || '')}</td><td>${escapeHtml(h.task || '')}</td><td>${escapeHtml(h.model || '')}</td><td>${(h.prompt_tokens || 0).toLocaleString()}</td><td>${(h.completion_tokens || 0).toLocaleString()}</td><td>${(h.total_tokens || 0).toLocaleString()}</td></tr>`;
    }
    historyHtml += '</table>';

    pane.innerHTML = `<div style="padding:var(--space-2)">${totalHtml}${modelHtml}${taskHtml}${historyHtml}</div>`;
  } catch (e) {
    pane.innerHTML = `<p class="muted">加载失败: ${escapeHtml(e.message || e)}</p>`;
  }
}
```

- [ ] **Step 8.4: Add tokens branch in utils.js**

In `updateEntityUI()`, after the `logs` branch:
```js
} else if (state.currentEntity === 'tokens') {
  document.querySelector('.project-item[data-entity="tokens"]').classList.add('active');
  $$('.video-item').forEach(v => v.classList.remove('active'));
}
```

Also update the entity class name switch (line ~78):
```js
const cls = state.currentEntity === 'plan' ? 'entity-plan'
  : state.currentEntity === 'run' ? 'entity-run'
  : state.currentEntity === 'config' ? 'entity-config'
  : state.currentEntity === 'logs' ? 'entity-logs'
  : state.currentEntity === 'tokens' ? 'entity-tokens'
  : 'entity-video';
```

- [ ] **Step 8.5: Add click binding in main.js**

In the sidebar click handler (line ~165), add after the `logs` branch:
```js
else if (p.dataset.entity === 'tokens') selectTokens();
```

Add import:
```js
import { selectTokens } from './sidebar.js';
```

- [ ] **Step 8.6: Add CSS in style.css**

Add after `entity-logs` CSS block:
```css
#editor.entity-tokens .tabs { display: none; }
#editor.entity-tokens .tab-pane:not(#tab-tokens) { display: none; }
#editor.entity-tokens #tab-tokens { display: block; }
#editor.entity-tokens .editor-actions { display: none; }

.token-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  min-width: 140px;
  text-align: center;
}
.token-card-value {
  font-size: 1.6em;
  font-weight: 700;
  color: var(--accent);
}
.token-card-label {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: 2px;
}
.token-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
  margin-bottom: var(--space-3);
}
.token-table th, .token-table td {
  padding: 4px 8px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
.token-table th {
  color: var(--text-tertiary);
  font-weight: 600;
  position: sticky;
  top: 0;
  background: var(--bg-base);
}
.token-time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
}
```

- [ ] **Step 8.7: Verify no JS syntax errors**

```bash
.\.venv\Scripts\python.exe -c "
import re
files = [
  'vlog_tool/ui/static/src/utils.js',
  'vlog_tool/ui/static/src/editor.js',
  'vlog_tool/ui/static/src/sidebar.js',
  'vlog_tool/ui/static/src/main.js',
]
for f in files:
  with open(f, encoding='utf-8') as fh:
    content = fh.read()
  # Basic check: matching braces
  opens = content.count('{')
  closes = content.count('}')
  print(f'{f}: braces {opens}/{closes} ', end='')
  print('OK' if opens == closes else 'MISMATCH')
"
```

- [ ] **Step 8.8: Commit**

```bash
git add vlog_tool/ui/static/index.html vlog_tool/ui/static/src/sidebar.js vlog_tool/ui/static/src/editor.js vlog_tool/ui/static/src/utils.js vlog_tool/ui/static/src/main.js vlog_tool/ui/static/style.css
git commit -m "feat(ui): add Tokens sidebar entity with usage statistics panel"
```

---

### Task 9: Verify Full Integration

- [ ] **Step 9.1: Run Python import check on all changed modules**

```bash
.\.venv\Scripts\python.exe -c "
from vlog_tool.ai.base import TokenUsage, AIResponse, TaskName
from vlog_tool.ai.token_usage import TokenUsageStore, FileTokenUsageStore
from vlog_tool.ai.gemini import GeminiProvider
from vlog_tool.ai.openai_compat import OpenAICompatProvider
from vlog_tool.analyze import analyze_video, generate_voiceover, plan_daily_vlog, refine_text, refine_script
from vlog_tool.tasks.analyze import run_analyze_all
from vlog_tool.tasks.scripts import run_generate_scripts
from vlog_tool.tasks.refine import run_refine_texts, run_refine_scripts
from vlog_tool.tasks.plan import run_plan_vlog
from vlog_tool.ui.routes.token_routes import handle_get_token_usage
print('All imports OK')
"
```

- [ ] **Step 9.2: Run existing tests to verify no regressions**

```bash
.\.venv\Scripts\python.exe -m pytest vlog_tool/tests/ -x -q 2>&1 | tail -20
```

Expected: all tests pass (612 cases).

- [ ] **Step 9.3: Manual smoke test — FileTokenUsageStore**

```bash
.\.venv\Scripts\python.exe -c "
from pathlib import Path
import tempfile, os
from vlog_tool.ai.base import TokenUsage
from vlog_tool.ai.token_usage import FileTokenUsageStore

with tempfile.TemporaryDirectory() as d:
    s = FileTokenUsageStore(d)
    s.record('video_analyze', 'gemini-2.0-flash', TokenUsage(100, 20, 120))
    s.record('voiceover', 'deepseek-chat', TokenUsage(50, 10, 60))
    stats = s.get_stats()
    assert stats['total']['total_tokens'] == 180, f'total mismatch: {stats[\"total\"][\"total_tokens\"]}'
    assert stats['by_model']['gemini-2.0-flash']['calls'] == 1
    assert stats['by_task']['video_analyze']['total_tokens'] == 120
    assert len(stats['history']) == 2
    print('Smoke test PASSED')
"
```

- [ ] **Step 9.4: Final status check**

```bash
git status
git log --oneline -5
```
