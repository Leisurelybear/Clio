# R-017: Model Registry & Task Binding UI

> Design doc for replacing the generic Settings AI config form with a structured
> model registry (provider list) and task binding panel.
> Signed off 2026-07-02.

## 1. Motivation

Users currently must manually edit `config.yaml` / `project.yaml` to manage AI
providers and task bindings — typing provider names, model strings, and API keys
by hand. This is error-prone and unfriendly. Goal: a visual model registry where
users can register providers, manage API keys, and bind tasks via dropdowns with
capability-based filtering.

## 2. Architecture Decision

**Pure frontend replacement** — no new backend CRUD endpoints. The existing
`PUT /api/config/global` and `PUT /api/config/project` endpoints are reused.
Capability validation (gemini → video tasks) is computed on the frontend.

**Where it lives**: inside the existing **Settings** tab, replacing only the
`ai.providers` (Global sub-tab) and `ai.tasks` (Project sub-tab) sections with
structured forms. Other config sections keep the generic form renderer.

## 3. Data Model Change

`ProviderConfig` in `clio/config/models.py` gains an optional `models` field:

```python
@dataclass
class ProviderConfig:
    name: str
    type: str                          # "gemini" | "openai"
    api_key: str = ""
    api_key_env: str = ""
    base_url: str = ""
    poll_interval_sec: int = 5
    retry_attempts: int = 2
    requests_per_minute: int = 0
    max_tokens: int = 4096
    models: list[str] = field(default_factory=list)   # ← NEW
```

- `models` lists the model names this provider supports
  (e.g. `["gemini-2.5-flash", "gemini-2.0-flash"]`)
- YAML representation: `models: [gemini-2.5-flash, gemini-2.0-flash]`
- `TaskConfig` is unchanged — task bindings still store `{provider, model}`
- `_parse_providers()` in `parsers.py` reads `models` from YAML
- Missing field → empty list (backward compatible)

## 4. Backend Changes

| File | Change |
|---|---|
| `clio/config/models.py` | `ProviderConfig.models` field |
| `clio/config/parsers.py` | `_parse_providers()` reads `models` |
| `clio/config/descriptions.py` | Add `ai.providers.{name}.models` description |
| `clio/ui/routes/config_routes.py` | No change (reuses existing PUT) |
| `tests/` | Update ProviderConfig tests for `models` |

No new API routes. No schema migration needed (field is optional).

## 5. Frontend: Provider List (Settings → Global sub-tab)

Replaces the generic `ai.providers` form with a structured card list.

### Layout
```
┌─ AI 模型列表 ──────────────────────────────────────────────┐
│                                                             │
│  [gemini]                 ⚠️ 未注册模型        [编辑] [删除] │
│  ─────────────────────────────────────────                  │
│  类型       gemini                                          │
│  API 密钥   •••••••••••••                   [显示/隐藏]     │
│  模型       (空 — 请编辑添加模型)                            │
│                                                             │
│  [deepseek]                                [编辑] [删除]     │
│  ─────────────────────────────────────────                  │
│  类型       openai                                          │
│  API 密钥   •••••••••••••                                   │
│  接口地址   https://api.deepseek.com/v1                     │
│  模型       [deepseek-chat] [deepseek-v4-flash]             │
│                                                             │
│                                        [+ 添加 Provider]    │
└─────────────────────────────────────────────────────────────┘
```

### Add/Edit Provider Modal

| Field | Control | Notes |
|---|---|---|
| 名称 | `<input>` | Unique identifier, e.g. `my-gemini` |
| 类型 | `<select>` | `gemini` / `openai` |
| API 密钥 | `<input type="password">` + toggle | Auto-saved to `.env` as `{NAME}_API_KEY` |
| 接口地址 | `<input>` | Only shown for `type=openai`; default `https://api.openai.com/v1` |
| 模型列表 | Tag input (chips) | Type + Enter/Space to add; × to remove |

### API Key Flow (Gap 1 fix)
1. User enters API key in form
2. Frontend generates env var name: `sanitize(name).toUpper() + "_API_KEY"`
3. Calls `PUT /api/env` with content `{NAME}_API_KEY=xxxxx`
4. Sets `api_key_env: {NAME}_API_KEY` (api_key field left empty)

### Delete Safety (Gap 4 fix)
- Before deletion: fetch project-level `ai.tasks`, check if any task references this provider
- If referenced: show modal with list of affected tasks + confirm/cancel
- Example: `"以下任务正在使用 deepseek：voiceover、vlog_plan。确定删除？"`

### Rename Safety (Gap 4 fix)
- When saving a provider with a new name: auto-update all task bindings in project config
- Show confirmation: `"将同时更新 N 个任务中的 provider 名称"`

### Empty State (Gap 2 fix)
- No providers: display "还没有注册任何 AI 模型" with brief explanation

## 6. Frontend: Task Binding (Settings → Project sub-tab)

Replaces the generic `ai.tasks` form with a structured binding panel.

### Layout
```
┌─ AI 任务绑定 ─────────────────────────────────────────────────┐
│                                                                │
│  视频分析 (video_analyze)                                      │
│  ┌─ Provider: [  gemini            ▼] ──────────────────────┐  │
│  └─ Model:    [  gemini-2.5-flash  ▼] ──────────────────────┘  │
│                                                                │
│  口播文案 (voiceover)                                          │
│  ┌─ Provider: [  deepseek          ▼] ──────────────────────┐  │
│  └─ Model:    [  deepseek-chat     ▼] ──────────────────────┘  │
│                                                                │
│  vlog 剪辑规划 (vlog_plan)                                     │
│  ┌─ Provider: [  deepseek          ▼] ──────────────────────┐  │
│  └─ Model:    [  deepseek-chat     ▼] ──────────────────────┘  │
│                                                                │
│  文本精修 (refine_text)                                        │
│  ┌─ ☑ 跟随视频分析 ─────────────────────────────────────────┐  │
│  │  (取消勾选后可独立选择)                                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                │
│                                              [保存到 project.yaml] │
└────────────────────────────────────────────────────────────────┘
```

### Provider Dropdown Filtering
- **video_analyze**: only `type=gemini` providers (video-capable)
- **voiceover / vlog_plan / refine_text**: all providers

### Model Dropdown
- Shows models from selected provider's `models` list
- Empty → hint: `"该 Provider 没有注册可用模型，请先编辑 Provider"`

### Refine Text Follow Logic (Gap 6 fix)
- Default: checkbox checked → `refine_text` not saved to `project.yaml` → runtime auto-fallback to `video_analyze`
- Unchecked: show independent provider/model dropdowns → saves `refine_text` to `project.yaml`
- Re-checked: remove `refine_text` from `project.yaml` → restores auto-fallback

### Cross-Tab Navigation (Gap 5 fix)
- If no providers exist: banner `⚠️ 请先在 AI 模型列表中添加 Provider` + **[去添加]** button
- Button click: switches Settings tab to Global sub-tab, auto-scrolls to AI model section

## 7. Tag Input Component (Gap 7 fix)

Reusable chip/tag input component in `editor-config.js`:

```javascript
function _renderTagInput(container, values, onChange) {
  // container.innerHTML = chip list + input field
  // Type Enter/Space → add chip
  // Click × on chip → remove
  // Backspace on empty input → remove last chip
  // onChange callback fires on any change
}
```

Styling matches existing chip patterns in the project (rounded background blocks,
× delete button, `--accent` color scheme).

## 8. Migration

- Existing providers in `config.yaml` appear automatically in the new card list
- `models` field defaults to empty list for existing providers
- Existing task bindings continue to work as-is
- Users are prompted to register models when they edit a provider that has none

## 9. Files Changed

| File | Change Type | Description |
|---|---|---|
| `clio/config/models.py` | Edit | Add `models: list[str]` to `ProviderConfig` |
| `clio/config/parsers.py` | Edit | Read `models` in `_parse_providers()` |
| `clio/config/descriptions.py` | Edit | Add description for `models` field |
| `clio/ui/static/src/editor-config.js` | Edit | Replace AI sections with structured forms |
| `clio/ui/static/style.css` | Edit | Provider cards, tag input, modal styles |
| `clio/tests/test_config.py` | Edit | Update ProviderConfig tests for `models` |

## 10. Out of Scope (Future)

- Multi-model comparison per task (part of R-010)
- Anthropic adapter support (requires new provider class)
- Live key validation ("Test Connection" button)
