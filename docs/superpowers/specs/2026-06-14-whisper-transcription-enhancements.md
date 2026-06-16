# Whisper 转录增强：调序 / 单视频逐条执行 / Plan 开关

## 背景

Whisper ASR 转录已作为独立 pipeline step 实现，但现有三处不足：

1. **Pipeline 位置不合适** — transcribe 当前在 compress 之后、analyze 之前，但实际使用中应该在 voiceover（口播）之后、plan（剪辑规划）之前，因为 transcript 主要用于优化 plan 的 prompt
2. **不支持单视频执行** — UI 只有 pipeline 批量运行，不能像 analyze/voiceover 那样从侧栏下拉菜单对单个视频逐条转录
3. **Plan 缺乏 transcript 开关** — transcript 自动注入到 PLAN_PROMPT，无法关闭；部分场景（如已有手工剪辑方案）不需要 AI 参考口播内容

此外，测试发现：当 faster-whisper 未安装时，run tab 的 pipeline 执行静默跳过，UI 不显示警告。

## 1. Pipeline 步骤调序

### 改动

| 位置 | 当前顺序 | 新顺序 |
|------|----------|--------|
| `pipeline.py` `_STEP_LABELS` / `_STEP_FUNCS` | compress → **transcribe** → analyze → voiceover → plan → label | compress → analyze → voiceover → **transcribe** → plan → label |
| `runner.js` `RUN_STEPS` | 同上 | 同上 |
| `sidebar.js` `renderSteps` labels | 同上 | 同上 |

### 影响

- plan 步骤在 transcribe 之后，保证 `{transcripts_json}` 注入时文件已就位
- `run_pipeline_steps` 无需改，`steps` 参数是 list，顺序由 dict 决定 — 需调 `_STEP_LABELS` 和 `_STEP_FUNCS` 的声明顺序（Python 3.7+ 保持插入顺序）
- `run_transcribe_all` 的 `total` 计算基于 `compressed_dir`，不依赖步骤顺序，无影响

## 2. 单视频逐条转录（原视频视图）

### 前端

`sidebar.js` — 原视频视图下拉菜单（`state.source === 'original'`），在「压缩视频」<button>之后添加：

```javascript
<button class="menu-item" data-action="transcribe" title="用 faster-whisper 提取音频转文字">Whisper 转录</button>
```

原视图的 analyze/voiceover/all 保持 disabled（灰色）。

### 后端

`routes/run.py:handle_post_rerun` — 验证列表加 `"transcribe"`：

```python
task not in ("compress", "analyze", "texts", "voiceover", "transcribe", "all")
```

`_rerun_worker` 函数加分支：

```python
if task in ("transcribe", "all"):
    from vlog_tool.tasks.transcribe import run_transcribe_one
    _log("Step: transcribing audio...")
    result = run_transcribe_one(cfg, original_video)
    if "error" in result:
        _log(f"✗ transcription failed: {result['error']}")
        raise RuntimeError(result["error"])
    _log("✓ transcription complete")
```

注意：transcribe 仅在原视频视图触发，`source_view` 为 `"original"`，`original_video` 直接取 `proj_input / video_basename`。

### 并发

与 analyze/voiceover 共用 `_run_lock`，同一时间只能跑一个。

## 3. Plan transcript 开关

### Config

`config.py` — `PlanConfig` 加字段：

```python
use_transcripts: bool = True
```

### Analyzer

`analyze.py:plan_daily_vlog()` — 签名为：

```python
def plan_daily_vlog(clips, config, day_label="day1",
                    transcripts_map=None, use_transcripts=True):
```

将内部 `if transcripts_map and config.whisper.enabled:` 改为：

```python
if transcripts_map and use_transcripts and config.whisper.enabled:
```

### Tasks/Plan

`tasks/plan.py` — 加载 transcripts_map 后传给 `plan_daily_vlog` 时加开关：

```python
plan = plan_daily_vlog(clips, config, day_label,
                       transcripts_map=transcripts_map,
                       use_transcripts=config.plan.use_transcripts)
```

### CLI

`main.py` — plan/analyze-all subcommand 加 `--no-transcripts` flag：

```python
p_plan.add_argument("--no-transcripts", action="store_true",
                    help="不注入语音转录信息")
```

dispatch 中覆写 config：

```python
config.plan.use_transcripts = not getattr(args, "no_transcripts", False)
```

### UI run tab

`runner.js` — run tab 表单加 checkbox（在 step checklist 之后）：

```html
<div class="run-options">
  <label class="run-option">
    <input type="checkbox" id="run-use-transcripts" checked>
    <span>使用语音转录优化剪辑规划</span>
  </label>
</div>
```

`startRun` 中附加到 POST body：

```javascript
const r = await api('POST', '/api/run/start', {
  day_label: _lastRunDay,
  steps: checked,
  use_transcripts: $('run-use-transcripts').checked,
});
```

`routes/run.py:handle_post_run_start` — 从 obj 读取 `use_transcripts`，注入 cfg：

```python
if "use_transcripts" in obj:
    cfg.plan.use_transcripts = obj["use_transcripts"]
```

### config.example.yaml

plan 节加注释行：

```yaml
#   use_transcripts: true
```

## 4. 错误处理：faster-whisper 未安装时 UI 报错

### Bug

`run_transcribe_all` 中当 `_check_whisper()` 失败时打印警告后 `return 0`，pipeline runner 视作成功，UI 显示「完成」。

### 修复

`tasks/transcribe.py` — `run_transcribe_all` 增加 `tracker` 通知：

```python
def run_transcribe_all(config, tracker=None):
    if not config.whisper.enabled:
        print("Whisper 转录未启用...")
        return 0
    if not check_whisper():
        msg = "faster-whisper 未安装，跳过转录。执行: python main.py whisper install"
        print(f"警告：{msg}")
        if tracker:
            tracker.error(msg)
        return 0
    # ... rest
```

### 测试

- `test_tasks_transcribe.py` — 检查未安装时 `tracker.error()` 被调用
- `test_routes_run.py` — 检查 `"transcribe"` 在 task 验证列表中
- `test_main.py` — 检查 `--no-transcripts` flag 解析

## 5. 文件清单

| 文件 | 改动 |
|------|------|
| `vlog_tool/config.py` | `PlanConfig.use_transcripts` 字段 |
| `vlog_tool/pipeline.py` | 调 `_STEP_LABELS/_STEP_FUNCS` 声明顺序 |
| `vlog_tool/tasks/transcribe.py` | `run_transcribe_all` 加 `tracker.error()` |
| `vlog_tool/analyze.py` | `plan_daily_vlog` 加 `use_transcripts` 参数 |
| `vlog_tool/tasks/plan.py` | 传 `use_transcripts` 给 plan_daily_vlog |
| `main.py` | `plan` subcommand 加 `--no-transcripts` |
| `vlog_tool/ui/routes/run.py` | rerun 加 `"transcribe"` 分支；run start 读 `use_transcripts` |
| `vlog_tool/ui/static/src/sidebar.js` | 原视频菜单加「Whisper 转录」按钮 |
| `vlog_tool/ui/static/src/runner.js` | 调 `RUN_STEPS` 顺序；加 `use_transcripts` checkbox |
| `vlog_tool/tests/test_tasks_transcribe.py` | 加未安装时 tracker.error 测试 |
| `vlog_tool/tests/test_routes_run.py` | 加 transcribe rerun 测试 |
| `vlog_tool/tests/test_main.py` | 加 `--no-transcripts` 测试 |
| `config.example.yaml` | plan 节加 `use_transcripts` 注释 |
