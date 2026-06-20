# Config Descriptions UI + Test Expansion Design

## 1. Summary

Two independent but related improvements:
1. Add Chinese descriptions to every config field in the Web UI, shown via hover tooltip (ⓘ icon)
2. Expand test coverage: new UI tests for config rendering + new Python tests for config routes, server dispatch, and schema integrity

## 2. Config Descriptions — Data Source

### 2.1 Description Dictionary

New file: `vlog_tool/config/descriptions.py`

```python
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
    # ai.providers.<name>.type
    "ai.providers.{name}.type": "AI 厂商类型：gemini（多模态）或 openai（纯文本兼容）",
    "ai.providers.{name}.api_key_env": "API 密钥的环境变量名（如 GEMINI_API_KEY），而非密钥本身",
    "ai.providers.{name}.api_key": "API 密钥（直接填入，优先级低于 api_key_env）",
    "ai.providers.{name}.base_url": "API 基础地址，兼容 OpenAI 格式的厂商需要填写",
    "ai.providers.{name}.poll_interval_sec": "Gemini 文件处理状态轮询间隔（秒）",
    "ai.providers.{name}.retry_attempts": "额外重试次数（默认 2，总计尝试 3 次）",
    "ai.providers.{name}.requests_per_minute": "每分钟最多调用次数，0 为不限流",
    "ai.providers.{name}.max_tokens": "AI 输出最大 token 数",
    # ai.tasks.<name>
    "ai.tasks.{name}.provider": "此任务使用的 AI 厂商名称（在 providers 中定义）",
    "ai.tasks.{name}.model": "模型名称，如 gemini-2.5-flash、deepseek-chat",
    # ai
    "ai.context": "项目特定背景信息，自动注入到所有 AI 提示词前",
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
    "analyze.skip_existing": "跳过已处理的文件（全局开关，影响所有步骤）",
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
    "whisper.model_size": "Whisper 模型大小：small（快速）、medium（平衡）、large-v3（高精度）",
    "whisper.language": "转录语言：zh（中文）、en（英文）、auto（自动检测）",
    "whisper.device": "计算设备：auto（自动）、cpu（CPU）、cuda（GPU）",
    "whisper.max_segments_per_clip": "每段视频最多取前 N 条转录结果注入规划",
    "whisper.cache_dir": "Whisper 模型缓存目录，null 使用程序默认路径",
    "whisper.transcripts_subdir": "转录结果存放的子目录名",
    "whisper.hf_endpoint": "HuggingFace 镜像地址，国内推荐 hf-mirror.com，留空用官方",
}
```

For dynamic keys like `ai.providers.<name>.type`, the tooltip is attached to the value field.

### 2.2 API Integration

- `config_routes.py`: `handle_get_config_raw` adds `_descriptions` to the response JSON
- The descriptions dict is loaded once from `vlog_tool.config.descriptions.CONFIG_DESCRIPTIONS`

## 3. Config Descriptions — UI Rendering

### 3.1 Display Form: ⓘ Tooltip

Approach B: A small ⓘ icon (info circle) rendered next to each config field label.
- On mouse hover: shows a tooltip popup with the description text
- On click (touch devices): toggles tooltip visibility
- Auto-dismiss on mouse leave or clicking elsewhere

### 3.2 Implementation

#### CSS (style.css)
```css
.config-desc-icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--border-light); color: var(--text-secondary);
  font-size: 10px; cursor: help; margin-left: 6px;
  flex-shrink: 0; position: relative;
}
.config-desc-tooltip {
  display: none; position: absolute; z-index: 100;
  bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%);
  background: var(--bg-surface); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 6px 10px; font-size: var(--text-xs); line-height: 1.4;
  white-space: normal; min-width: 200px; max-width: 320px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15); pointer-events: none;
}
.config-desc-icon:hover .config-desc-tooltip,
.config-desc-icon.show .config-desc-tooltip { display: block; }
```

#### JS (editor.js — `_renderConfigForm`)
Modify the rendering to:
1. After generating field label HTML, append ⓘ icon if a description exists for the current path
2. Store descriptions in a module-level lookup via `state.configDescriptions`

The `_renderConfigForm` function receives an additional `descriptions` parameter (or accesses it from state). When `descriptions[path]` exists, a tooltip icon is appended to the label.

For provider/task dynamic names (like `ai.providers.gemini`), the description lookup keys to `ai.providers.{name}` pattern are matched via prefix and suffix.

### 3.3 Tooltip Behavior

- Desktop: `:hover` CSS trigger
- Mobile: click toggle via JS (`el.classList.toggle('show')`)
- Close when clicking outside (document click listener)

## 4. Test Expansion

### 4.1 UI Tests (Vitest + jsdom)

**New file:** `vlog_tool/ui/static/src/__tests__/editor.test.js`

Test cases for `_renderConfigForm` (exported for testing):

| # | Test | Description |
|---|------|-------------|
| 1 | renders null | Shows `(空)` span |
| 2 | renders boolean | Shows checkbox input |
| 3 | renders number | Shows number input with correct step |
| 4 | renders short string | Shows text input |
| 5 | renders pwd string | Shows password input for `api_key` paths |
| 6 | renders multiline string | Shows textarea for long/texts |
| 7 | renders ai.context | Shows textarea with context hint |
| 8 | renders object | Shows fieldset with nested entries |
| 9 | renders string array | Shows textarea with per-line hint |
| 10 | renders mixed array | Shows array-item divs |
| 11 | renders description tooltip | ⓘ icon present when description exists |
| 12 | renderConfig renders init view | When `_needsConfigInit` is true, shows init UI |
| 13 | renderConfig renders normal view | Config form with proper structure |
| 14 | change handlers bind correctly | `onchange` / `oninput` call `setDeep` |
| 15 | env editor toggle | Button click shows/hides editor |

All tests mock `$()` (DOM lookup) and test function outputs without real DOM (or use jsdom minimal setup).

**Modifications to editor.js for testability:**
- Export `_renderConfigForm`, `labelFromPath`, `renderConfig` for testing (currently module-scoped functions)

### 4.2 Python Tests

#### New: `test_routes_config.py` additions (6 → 14 tests)

| # | Test | Description |
|---|------|-------------|
| 7 | put failures on yaml parse error | `handle_put_config_raw` returns error when YAML invalid |
| 8 | put global config update | Writing to default project writes to global config.yaml |
| 9 | init creates project.yaml | `handle_post_config_init` creates valid project.yaml for non-default |
| 10 | get config raw includes descriptions | Response has `_descriptions` key |
| 11 | get config raw for default project | Default project returns merged config without `needs_init` |
| 12 | put config with invalid type coerce | Numbers in string fields get coerced |
| 13 | put config restores backup on failure | If save fails, old config is restored |
| 14 | config cache invalidated after put | `_config_cache.invalidate_all` or `invalidate_key` called |

#### New: `test_routes_env.py` (8 tests)

| # | Test | Description |
|---|------|-------------|
| 1 | get env returns content | `handle_get_env` returns `.env` content |
| 2 | get env returns template when missing | No `.env` → template string returned |
| 3 | put env saves content | `handle_put_env` writes to `.env` |
| 4 | put env reloads vars | `_load_dotenv` called after save |
| 5 | put env invalidates cache | Config cache cleared |
| 6 | put env returns path | Response includes save path |
| 7 | get env with project dir | Project-specific `.env` returned |
| 8 | put env to project dir | Saves to project-specific `.env` |

#### New: `test_config_descriptions.py` (5 tests)

| # | Test | Description |
|---|------|-------------|
| 1 | all model fields have descriptions | Every field in every config dataclass has a description entry |
| 2 | no extra descriptions | Every description key maps to an actual field |
| 3 | descriptions are non-empty | Every description has text |
| 4 | descriptions for provider tasks | Pattern keys match dynamic provider/task names |
| 5 | descriptions don't contain secrets | No API keys or sensitive info in descriptions |

## 5. Files Changed

### Backend
- `vlog_tool/config/descriptions.py` — NEW, description dictionary
- `vlog_tool/config/__init__.py` — export `CONFIG_DESCRIPTIONS`
- `vlog_tool/ui/routes/config_routes.py` — add `_descriptions` to `handle_get_config_raw` response
- `vlog_tool/tests/test_config_descriptions.py` — NEW, 5 tests
- `vlog_tool/tests/test_routes_config.py` — +8 tests (6→14)
- `vlog_tool/tests/test_routes_env.py` — NEW, 8 tests

### Frontend
- `vlog_tool/ui/static/src/editor.js` — export `_renderConfigForm`, add tooltip rendering
- `vlog_tool/ui/static/style.css` — tooltip styles
- `vlog_tool/ui/static/src/__tests__/editor.test.js` — NEW, 15 tests

## 6. Constraints & Security

- No descriptions contain real API keys, paths, or sensitive info
- External HTTP requests mocked in tests (no real Gemini/DeepSeek calls)
- Tooltip content is static text from Python dict, no user-injectable content
- UI tests use jsdom, no real browser required
