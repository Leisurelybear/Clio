# Config Descriptions + Test Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Chinese descriptions (ⓘ tooltip) to every config field in Web UI, and expand test coverage with 28+ new tests.

**Architecture:** Backend: `config/descriptions.py` defines all descriptions → config route includes them in API response → frontend `editor.js` renders ⓘ icon next to each field with hover tooltip. Tests: Python (pytest) for backend schema/routes, JS (vitest+jsdom) for frontend rendering.

**Tech Stack:** Python 3.11+, pytest, vitest+jsdom, plain JS/ES modules

---

### File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `vlog_tool/config/descriptions.py` | **Create** | `CONFIG_DESCRIPTIONS` dict mapping field paths→Chinese text |
| `vlog_tool/config/__init__.py` | **Modify** | Export `CONFIG_DESCRIPTIONS` |
| `vlog_tool/ui/routes/config_routes.py` | **Modify** | Add `_descriptions` to `handle_get_config_raw` response |
| `vlog_tool/ui/static/src/editor.js` | **Modify** | Export `_renderConfigForm`, add tooltip rendering |
| `vlog_tool/ui/static/style.css` | **Modify** | Tooltip icon + popup styles |
| `vlog_tool/tests/test_config_descriptions.py` | **Create** | 5 schema-integrity tests |
| `vlog_tool/tests/test_routes_config.py` | **Modify** | +8 tests (6→14) |
| `vlog_tool/tests/test_routes_env.py` | **Create** | 8 env route tests |
| `vlog_tool/ui/static/src/__tests__/editor.test.js` | **Create** | 15 UI tests |

---

### Task 1: Create descriptions.py

**Files:**
- Create: `vlog_tool/config/descriptions.py`
- Modify: `vlog_tool/config/__init__.py` (export)

- [ ] **Step 1: Write descriptions.py**

```python
"""Chinese descriptions for every config field. Used by UI to show ⓘ tooltips."""

CONFIG_DESCRIPTIONS: dict[str, str] = {
    # paths
    "paths.input_dir": "原始视频所在目录，所有视频文件从此目录读取",
    "paths.output_dir": "所有输出文件（压缩、转录、文案等）的根目录",
    "paths.recursive": "是否递归扫描子文件夹内的所有视频",
    "paths.ffmpeg": "ffmpeg 可执行文件路径，留空则自动搜索",
    "paths.ffprobe": "ffprobe 可执行文件路径，留空则自动搜索",
    "paths.logs_dir": "日志目录，按小时切文件：YYYY-MM-DD-HH.log",

    # proxy
    "proxy.enabled": "是否启用代理（访问 Gemini 等需要）",
    "proxy.url": "代理地址，如 socks5://127.0.0.1:1080",

    # ai
    "ai.context": "项目特定背景信息，每次 AI 调用前自动注入到提示词前面",

    # ai.providers.* (pattern key for dynamic names)
    "ai.providers.{name}.type": "AI 厂商类型：gemini（多模态视频理解）或 openai（纯文本兼容接口）",
    "ai.providers.{name}.api_key_env": "API 密钥的环境变量名（如 GEMINI_API_KEY），而非密钥本身",
    "ai.providers.{name}.api_key": "API 密钥（直接填入，优先级低于 api_key_env）",
    "ai.providers.{name}.base_url": "API 基础地址，OpenAI 兼容接口需要填写",
    "ai.providers.{name}.poll_interval_sec": "Gemini 文件处理状态轮询间隔（秒）",
    "ai.providers.{name}.retry_attempts": "额外重试次数（默认 2，总计尝试 3 次）",
    "ai.providers.{name}.max_tokens": "AI 输出最大 token 数",
    "ai.providers.{name}.requests_per_minute": "每分钟最多调用次数，0 为不限流",

    # ai.tasks.* (pattern key for dynamic task names)
    "ai.tasks.{name}.provider": "此任务使用的 AI 厂商名称（在 providers 中定义）",
    "ai.tasks.{name}.model": "模型名称，如 gemini-2.5-flash、deepseek-chat",

    # compress
    "compress.target_size_mb": "压缩后目标文件大小（MB）",
    "compress.max_width": "压缩后视频最大宽度（像素），高度按比例缩放",
    "compress.fps": "压缩后视频帧率",
    "compress.codec": "视频编码器，默认 libx264",
    "compress.crf": "CRF 压缩质量（0-51，越小质量越高，文件越大）",
    "compress.remove_audio": "是否移除音频（压缩后仅保留画面，可减小体积）",
    "compress.split_max_min": "超过此分钟数的视频，压缩前先自动分段。0 关闭分段",
    "compress.splits_subdir": "分段视频存放的子目录名",

    # analyze
    "analyze.compressed_subdir": "压缩视频存放的子目录名",
    "analyze.texts_subdir": "AI 分析结果（文案）存放的子目录名",
    "analyze.skip_existing": "全局跳过开关：跳过已处理的文件（影响所有步骤）",
    "analyze.max_analyze_duration_min": "超过此分钟数的压缩视频跳过 AI 分析。0 不限制",

    # naming
    "naming.index_width": "文件名中索引编号的位数（如 3 表示 001）",

    # script
    "script.scripts_subdir": "口播文案存放的子目录名",
    "script.template_file": "口播文案模板文件路径",
    "script.target_words": "单条口播文案的目标字数",

    # plan
    "plan.plans_subdir": "剪辑规划存放的子目录名",
    "plan.max_clips_per_day": "每日 vlog 最大片段数",
    "plan.target_duration_sec": "每日 vlog 目标时长（秒）",
    "plan.use_transcripts": "规划时是否注入语音转录内容作为参考",

    # whisper
    "whisper.enabled": "是否启用语音转录（需安装 faster-whisper）",
    "whisper.model_size": "Whisper 模型大小。small（快速）、medium（平衡）、large-v3（高精度）",
    "whisper.language": "转录语言。zh（中文）、en（英文）、auto（自动检测）",
    "whisper.device": "计算设备。auto（自动）、cpu（CPU）、cuda（GPU）",
    "whisper.max_segments_per_clip": "每段视频最多取前 N 条转录结果注入规划",
    "whisper.cache_dir": "Whisper 模型缓存目录，null 使用程序默认路径",
    "whisper.transcripts_subdir": "转录结果存放的子目录名",
    "whisper.hf_endpoint": "HuggingFace 镜像地址。国内推荐 hf-mirror.com，留空用官方",
}
```

- [ ] **Step 2: Export from __init__.py**

Edit `vlog_tool/config/__init__.py`. Add import line after existing imports and add to `__all__`:
```python
from vlog_tool.config.descriptions import CONFIG_DESCRIPTIONS
```
Add `"CONFIG_DESCRIPTIONS"` to the `__all__` list.

- [ ] **Step 3: Quick verify import works**

Run: `.\.venv\Scripts\python.exe -c "from vlog_tool.config.descriptions import CONFIG_DESCRIPTIONS; print(len(CONFIG_DESCRIPTIONS))"`
Expected: `44` (or the count of entries)

---

### Task 2: Add descriptions to config route response

**Files:**
- Modify: `vlog_tool/ui/routes/config_routes.py`

- [ ] **Step 1: Read current file first**

Run: Read the file to understand current implementation.

- [ ] **Step 2: Import CONFIG_DESCRIPTIONS and add to response**

Add at top imports:
```python
from vlog_tool.config.descriptions import CONFIG_DESCRIPTIONS
```

In `handle_get_config_raw`, before `handler._send_json`, add:
```python
payload["_descriptions"] = CONFIG_DESCRIPTIONS
```

---

### Task 3: Add tooltip rendering to editor.js

**Files:**
- Modify: `vlog_tool/ui/static/src/editor.js`

- [ ] **Step 1: Export _renderConfigForm and labelFromPath for testing**

At the top of editor.js, after the function definitions, add at the very end of the file (before the default exports):

```javascript
// Exported for testing
export { _renderConfigForm, labelFromPath };
```

Also ensure `renderConfig` and `renderActiveTab` are exported (they're used by main.js via dynamic import already).

- [ ] **Step 2: Modify _renderConfigForm to accept descriptions and render tooltip icon**

Change the function signature:
```javascript
function _renderConfigForm(obj, path, descriptions = null) {
```

At the very end of the file, before the export, add the description lookup helper:
```javascript
function _renderConfigForm(obj, path, descriptions = null) {
```

Actually, let me think about this more carefully. The current function is defined at line 823. I need to:
1. Add `descriptions` parameter
2. Update all recursive calls to pass `descriptions` through
3. Look up `descriptions[path]` and if found, append ⓘ icon to the field HTML

The tooltip icon should be a small circle with "?" that shows a tooltip popup on hover.

For the tooltip rendering, I'll need to:

a. Create a helper function that generates the tooltip HTML for a given path
b. Call it from the relevant rendering branches

Let me think about where the tooltip should appear. For:

- **Boolean field**: Tooltip next to the label text
- **Number field**: Tooltip next to the label  
- **String field (text/password)**: Tooltip next to the label
- **String field (textarea)**: Tooltip next to the label
- **Fieldset (object)**: Tooltip next to the legend

The tooltip HTML:
```html
<span class="config-desc-icon" data-path="${path}" role="tooltip" tabindex="0">
  <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor"><circle cx="8" cy="8" r="7"/><text x="8" y="9" text-anchor="middle" font-size="9" fill="white" font-weight="bold">?</text></svg>
  <span class="config-desc-tooltip">${escapeHtml(desc)}</span>
</span>
```

Now, let me plan the changes:

1. Change signature: `function _renderConfigForm(obj, path, descriptions = null)`
2. In each rendering branch, after the label text, conditionally add tooltip:
   ```javascript
   const label = labelFromPath(path);
   const tip = descriptions && descriptions[path] ? _renderTooltip(path, descriptions[path]) : '';
   ```
3. For objects, pass `descriptions` to recursive calls
4. For the `_renderTooltip` helper:

```javascript
function _renderTooltip(path, desc) {
  return `<span class="config-desc-icon" data-desc-path="${path}" tabindex="0">
    <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor"><circle cx="8" cy="8" r="7"/><text x="8" y="10" text-anchor="middle" font-size="9" fill="white" font-weight="bold">?</text></svg>
    <span class="config-desc-tooltip">${escapeHtml(desc)}</span>
  </span>`;
}
```

For the "contains child objects" fieldsets (like `ai.providers.gemini`), the tooltip for `ai.providers.{name}` pattern - I need to handle that. The descriptions dict has `ai.providers.{name}.type` but not `ai.providers.{name}`. 

Actually, looking at the design spec more carefully, for dynamic names the tooltip is attached to the value field, not the key. So for `ai.providers.gemini` → accessing `.type` field, the description would be `ai.providers.{name}.type`. 

I think for fieldsets (objects), we might want a tooltip on the fieldset legend too if a description exists for that path. Let me check if there are any object-level descriptions... Looking at the dict, there are no descriptions for intermediate nodes like `paths`, `compress`, etc. Just leaf fields. So the tooltip only goes on leaf nodes (booleans, numbers, strings).

For the renderConfig function, I need to:
1. Pass `state.configDescriptions` or extract descriptions from the state to `_renderConfigForm`
2. The descriptions come from `state.configRaw._descriptions`

So in `renderConfig()`:
```javascript
const { _config_source, _needsConfigInit, _descriptions, ...configData } = state.configRaw;
// ... later:
const descs = _descriptions || {};
pane.innerHTML = `...<div class="config-form">${_renderConfigForm(configData, '', descs)}</div>...`;
```

And in all the recursive calls within `_renderConfigForm`, pass `descriptions` through.

Let me also add a click event handler for mobile users:

```javascript
// Tooltip click toggle for touch devices
pane.querySelectorAll('.config-desc-icon').forEach(el => {
  el.onclick = (e) => {
    e.stopPropagation();
    el.classList.toggle('show');
  };
});
// Close tooltips on outside click
document.addEventListener('click', (e) => {
  if (!e.target.closest('.config-desc-icon')) {
    document.querySelectorAll('.config-desc-icon.show').forEach(el => el.classList.remove('show'));
  }
});
```

Wait, I should add the outside-click cleanup in renderConfig, and clean it up when re-rendering.

Actually, to keep it simple, I'll do it with CSS hover only for desktop. For mobile, the `:hover` will work as a click on most mobile browsers, so the CSS-only approach covers both. Let me add the `tabindex="0"` for keyboard focus as well.

But the design spec says "click toggle via JS" for mobile. Let me implement the JS toggle as described.

OK, let me now plan the exact edits.

Current code at line 823-865:
```javascript
function _renderConfigForm(obj, path) {
  if (obj === null || obj === undefined) {
    return `<span class="config-null">(空)</span>`;
  }
  if (typeof obj === 'boolean') {
    return `<label class="config-field config-bool"><span class="config-key">${labelFromPath(path)}</span> <input type="checkbox" data-path="${path}" ${obj ? 'checked' : ''}></label>`;
  }
  if (typeof obj === 'number') {
    const isInt = Number.isInteger(obj);
    return `<label class="config-field config-num"><span class="config-key">${labelFromPath(path)}</span> <input type="number" data-path="${path}" step="${isInt ? '1' : 'any'}" value="${obj}"></label>`;
  }
  if (typeof obj === 'string') {
    const multiline = path === 'ai.context' || obj.length > 80 || obj.includes('\n');
    if (multiline) {
      let hint = '';
      if (path === 'ai.context') {
        hint = '<br><span class="hint">项目特定背景（如拍摄地点、行程安排），将追加到默认模板 <code>trip_context.md</code> 之后。留空则仅使用默认模板。</span>';
      }
      return `<label class="config-field config-str"><span class="config-key">${labelFromPath(path)}</span> <textarea data-path="${path}" rows="4">${escapeHtml(obj)}</textarea>${hint}</label>`;
    }
    const isPwd = path.endsWith('api_key');
    return `<label class="config-field config-str"><span class="config-key">${labelFromPath(path)}</span> <input type="${isPwd ? 'password' : 'text'}" data-path="${path}" value="${escapeHtml(obj)}"></label>`;
  }
  if (Array.isArray(obj)) {
    const allStr = obj.every(x => typeof x === 'string');
    if (allStr) {
      return `<fieldset class="config-fieldset"><legend>${labelFromPath(path)}</legend><label class="config-field config-str"><textarea data-path="${path}" rows="${Math.max(2, obj.length)}">${escapeHtml(obj.join('\n'))}</textarea><span class="hint">每行一项</span></label></fieldset>`;
    }
    return `<fieldset class="config-fieldset"><legend>${labelFromPath(path)}</legend>${obj.map((item, i) =>
      `<div class="config-array-item">${_renderConfigForm(item, path + '[' + i + ']')}</div>`
    ).join('')}</fieldset>`;
  }
  if (typeof obj === 'object') {
    let html = `<fieldset class="config-fieldset"><legend>${labelFromPath(path) || '配置'}</legend>`;
    for (const [key, val] of Object.entries(obj)) {
      if (key === 'context_file') continue;
      html += _renderConfigForm(val, path ? `${path}.${key}` : key);
    }
    html += '</fieldset>';
    return html;
  }
  return `<span class="muted">${escapeHtml(String(obj))}</span>`;
}
```

I need to:
1. Change signature to `function _renderConfigForm(obj, path, descriptions = null)`
2. Add `_renderTooltip` helper
3. Add tooltip next to labels in string/bool/number branches
4. For object and array branches, pass `descriptions` to recursive calls
5. In `renderConfig`, extract `_descriptions` and pass it to the top-level call

Let me write this out precisely.

Actually, I realize I need to be really precise with the edit. Let me read the exact lines I'm editing.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="read">
<｜｜DSML｜｜parameter name="filePath" string="true">G:\Coding_Project\IdeaProjects\vlog-video-analysis\vlog_tool\ui\static\src\editor.js