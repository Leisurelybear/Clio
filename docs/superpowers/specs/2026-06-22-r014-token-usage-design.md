# R-014: AI Model Token Usage Statistics (Project Level)

## Background

Currently all AI calls only log prompt size and response size (bytes), with no per-token statistics. Users don't know how many tokens each project consumes, and cannot compare costs across models. Project-level token statistics help optimize model selection and cost control.

Both Gemini and OpenAI-compatible APIs return token usage data in their responses, but both are currently ignored.

## Architecture

```
                    ┌──────────────────────┐
                    │   TokenUsageStore     │  ← abstract interface
                    │   (ABC)              │
                    └──────────┬───────────┘
                               │ implements
                    ┌──────────┴───────────┐
                    │  FileTokenUsageStore  │  ← atomic .token_usage.json
                    └──────────────────────┘
                    
                    ┌──────────────────────┐
                    │      AIResponse      │  ← TextAIProvider return type
                    │  - text: str         │
                    │  - token_usage: ?    │
                    └──────────────────────┘
```

### Data Flow

```
pipeline step → analyze_video/generate_voiceover/...
                     ↓
               _call_ai(label, ..., fn, token_store)
                     ↓
               provider.generate_text(prompt, model)
                     ↓
               returns AIResponse(text="...", token_usage=TokenUsage(...))
                     ↓
               _call_ai: token_store.record(task, model, token_usage)
                     ↓
               returns text to caller (transparent)
```

### Storage Format (`output/.token_usage.json`)

```json
{
  "total": {
    "prompt_tokens": 15000,
    "completion_tokens": 3000,
    "total_tokens": 18000
  },
  "by_model": {
    "gemini-2.0-flash": {
      "prompt_tokens": 10000,
      "completion_tokens": 2000,
      "total_tokens": 12000,
      "calls": 5
    }
  },
  "by_task": {
    "video_analyze": {
      "prompt_tokens": 5000,
      "completion_tokens": 1000,
      "total_tokens": 6000,
      "calls": 3
    }
  },
  "history": [
    {
      "timestamp": "2026-06-22T10:30:00",
      "task": "video_analyze",
      "model": "gemini-2.0-flash",
      "prompt_tokens": 2000,
      "completion_tokens": 500,
      "total_tokens": 2500
    }
  ]
}
```

## Component Details

### 1. `ai/base.py` — New Types

```python
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

Change TextAIProvider:
```python
class TextAIProvider(Protocol):
    def generate_text(self, prompt: str, model: str) -> AIResponse: ...
```

Change VideoAIProvider:
```python
class VideoAIProvider(TextAIProvider, Protocol):
    def analyze_video(self, video_path: str, prompt: str, model: str, progress_callback=None) -> AIResponse: ...
```

### 2. `ai/token_usage.py` — New File

```python
class TokenUsageStore(ABC):
    def record(self, task: str, model: str, usage: TokenUsage) -> None: ...
    def get_stats(self) -> dict: ...
    def close(self) -> None: ...

class FileTokenUsageStore(TokenUsageStore):
    def __init__(self, output_dir: str): ...
    def record(self, task, model, usage): ...   # atomic append, thread-safe (Lock)
    def get_stats(self): ...                     # read + aggregate, empty if no file
    def close(self): ...                         # no-op for file backend
```

- Thread safety: `threading.Lock` around read-modify-write in `record()`
- Atomic writes: write to `.tmp` with random suffix → `os.replace()`
- Aggregate on read: keep raw history, generate stats on demand (fast aggregation over small history)
- No file → `get_stats()` returns empty structure: `{"total": {...0...}, "by_model": {}, "by_task": {}, "history": []}`

### 3. AI Provider Changes

**GeminiProvider** (`gemini.py`):

```python
def generate_text(self, prompt: str, model: str) -> AIResponse:
    def _do() -> AIResponse:
        self._maybe_wait()
        response = self._client.models.generate_content(model=model, contents=prompt)
        usage = None
        if response.usage_metadata:
            usage = TokenUsage(
                prompt_tokens=response.usage_metadata.prompt_token_count or 0,
                completion_tokens=response.usage_metadata.candidates_token_count or 0,
                total_tokens=response.usage_metadata.total_token_count or 0,
            )
        return AIResponse(text=response.text or "", token_usage=usage)
    return self._call_with_retry(_do, model, model)
```

Same pattern for `analyze_video()`.

**OpenAICompatProvider** (`openai_compat.py`):

```python
def generate_text(self, prompt: str, model: str) -> AIResponse:
    def _do() -> AIResponse:
        ...
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
    return with_retry(...)
```

### 4. `analyze.py` — Token Collection

`_call_ai()` signature updated to accept `token_store` + `task_name`:

```python
def _call_ai(label, provider_id, model, prompt, fn, *,
             debug_print=False, token_store=None, task_name=""):
    ...
    resp = fn()  # now returns AIResponse
    print(f"  响应: {format_size(len(resp.text.encode('utf-8')))}")
    if token_store and resp.token_usage:
        token_store.record(task_name or label, model, resp.token_usage)
    return resp.text
```

Each caller passes the corresponding `TaskName` value:
- `analyze_video`: `_call_ai("AI 视频分析", ..., task_name=TaskName.VIDEO_ANALYZE, token_store=token_store)`
- `generate_voiceover`: `_call_ai("AI 口播", ..., task_name=TaskName.VOICEOVER, token_store=token_store)`
- `plan_daily_vlog`: `_call_ai("AI vlog 剪辑规划", ..., task_name=TaskName.VLOG_PLAN, token_store=token_store)`
- `refine_text`: `_call_ai("AI refine 素材", ..., task_name=TaskName.REFINE_TEXT, token_store=token_store)`
- `refine_script`: `_call_ai("AI refine 脚本", ..., task_name=TaskName.REFINE_TEXT, token_store=token_store)`

All 5 top-level functions (`analyze_video`, `generate_voiceover`, `plan_daily_vlog`, `refine_text`, `refine_script`) add optional `token_store: TokenUsageStore | None = None` parameter, passed through to `_call_ai()`.

### 5. Pipeline Integration (`tasks/`)

Each task module creates `FileTokenUsageStore` at the start:

```python
def run_analyze_all(config, tracker=None, single_file=None, cancel_event=None):
    token_store = FileTokenUsageStore(config.paths.output_dir)
    ...
    analysis = analyze_video(str(compressed), config, progress_callback=_on_progress, token_store=token_store)
```

Same for `run_generate_scripts`, `run_refine_texts`, `run_refine_scripts`, `run_plan_vlog`.

### 6. Backend Route

```python
# ui/routes/token_routes.py
def handle_get_token_usage(handler, qs):
    proj_out = handler._project_output_dir(...)
    store = FileTokenUsageStore(proj_out)
    return handler._send_json(store.get_stats())
```

Registered in `server.py`:
```python
if path == "/api/token-usage":
    return handle_get_token_usage(self, qs)
```

### 7. UI — New Sidebar Entity

- Sidebar item between "运行" and "日志": `data-entity="tokens"` labeled "Tokens"
- `renderTokens()` shows:
  - Summary cards (total tokens, by model breakdown, by task breakdown)
  - History table (timestamp / task / model / prompt / completion / total)
  - Pure CSS, no chart library

### 8. CLI

```python
# main.py
p_tokens = sub.add_parser("tokens", help="查看 token 使用统计")
p_tokens.set_defaults(func=cmd_tokens)

def cmd_tokens(args):
    config = load_config(...)
    store = FileTokenUsageStore(config.paths.output_dir)
    stats = store.get_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
```

## Files Changed

See ROADMAP R-014 sub-tasks for detailed breakdown.

## Future Extensibility

- **New provider**: just implement `generate_text() -> AIResponse`
- **New task**: just pass `token_store` through
- **New storage backend**: implement `TokenUsageStore` ABC (SQLite, HTTP API)
- **New metadata**: add fields to `AIResponse` / `TokenUsage` — no interface change
- **Cost calculation**: add `model→price_per_token` mapping, compute cost on `get_stats()`
