# Whisper ASR 转录集成 — 设计文档

> 2026-06-14 · 基于 brainstorm 讨论定稿

---

## 1. Motivation & Background

当前 AI 分析仅基于**视频画面**理解内容，无法获知"人实际说了什么"。
Whisper ASR 转录提供带时间戳的口语文本，注入 plan 生成阶段后 AI 能：
- 判断哪段视频有实质口播内容，优先编排
- 理解`use_timeline` 范围内的人物对话背景
- 根据实际说话节奏建议更精准的片段时长

远期 option（**不在 Phase 1 范围内**）：transcript 摘要注入 refine 阶段，辅助修正分析/口播偏差。

---

## 2. Design Overview

**架构选择**：独立 pipeline step（`transcribe`），不经过 AI provider 层。
**转录对象**：对整个**原始视频**做一次转录（绝对时间轴），一份原始文件产一份 transcript JSON。
**时间轴映射**：split 段在 UI 中通过 `offset_sec` 换算显示/seek。
**注入目标**：`PLAN_PROMPT` 的 `{transcripts_json}` 变量，按 clip 注入高质量片段。

---

## 3. Config

```yaml
# config.yaml / project.yaml
whisper:
  enabled: false              # 开关，默认关闭
  model_size: medium          # 枚举：small | medium | large-v3
  language: zh                # 枚举：zh | en | auto（per-project，UI 下拉选择；auto=自动检测语言）
  device: auto                # 枚举：auto | cpu | cuda
  max_segments_per_clip: 5    # plan 注入时每段视频最多取 N 条 transcript
  cache_dir: null             # null=默认 <程序根目录>/models/
  transcripts_subdir: transcripts
```

`WhisperConfig` dataclass 定义在 `vlog_tool/config.py`，枚举使用 `StrEnum`：
- `WhisperModelSize("small" | "medium" | "large-v3")`
- `WhisperLang("zh" | "en" | "auto")`
- `WhisperDevice("auto" | "cpu" | "cuda")`

`WhisperConfig.sanitize()` 方法（dataclass 自身方法，遵循现有 config dataclass 风格）：
- `model_size` 不在枚举中 → raise `ValueError`
- `language` 不在枚举中 → raise `ValueError`；`auto` 时向 `model.transcribe()` 传 `language=None`
- `device` 不在枚举中 → raise `ValueError`
- `max_segments_per_clip < 1` → 重置为 5

**Per-project 覆盖**：`project.yaml` 可覆盖 `whisper.language` 实现按项目设置语言。
**未来视频级覆盖预留**：通过 `transcripts_meta.json`（当前不实现）。

---

## 4. Core Transcription — `vlog_tool/transcribe.py`

### `transcribe_audio(audio_path: Path, config: AppConfig, progress_callback=None) -> list[dict]`

职责：
1. 加载 `WhisperModel`（模块级缓存单例，同一 run 只加载一次）
2. 调用 `model.transcribe(audio_path, language=..., ...)`（VAD 过滤、beam_size=5）
   - `language` 从 config 读取，`auto` 时传 `language=None`
3. 过滤低置信度片段（`avg_logprob >= -0.8, no_speech_prob <= 0.1`）
4. 返回 segment 列表：`[{"start": float, "end": float, "text": str, "avg_logprob": float}]`

### 音频提取

转录前需用 ffmpeg 从视频中提取音频为 16kHz 单声道 WAV（Whisper 要求），位于 `vlog_tool/tasks/transcribe.py`：

```
ffmpeg -i <video> -vn -acodec pcm_s16le -ar 16000 -ac 1 <output.wav>
```

这是**重采样**操作（非简单 demux），但 ffmpeg 对此优化充分，GoPro 4K 源的提取时间通常在秒级。

单例缓存逻辑：
```python
_whisper_model: WhisperModel | None = None
_whisper_cache_key: str | None = None

def _get_model(config: AppConfig) -> WhisperModel:
    global _whisper_model, _whisper_cache_key
    cache_dir = _resolve_cache_dir(config)
    key = f"{config.whisper.model_size}@{cache_dir}"
    if _whisper_model is None or _whisper_cache_key != key:
        _whisper_model = WhisperModel(
            config.whisper.model_size,
            device=_resolve_device(config),
            compute_type=_resolve_compute_type(config),
            download_root=cache_dir,
        )
        _whisper_cache_key = key
    return _whisper_model
```

`_resolve_cache_dir(config)`：
- `config.whisper.cache_dir` 非空 → 使用它
- 否则 → `<main.py所在目录>/models/`
- 自动创建目录

`_resolve_device(config)` / `_resolve_compute_type(config)`：
- `auto`: CUDA 可用 → `("cuda", "int8_float16")`，否则 → `("cpu", "int8")`
- `cpu`: `("cpu", "int8")`
- `cuda`: `("cuda", "int8_float16")`

---

## 5. Pipeline Task — `vlog_tool/tasks/transcribe.py`

### `run_transcribe_all(config: AppConfig, tracker: ProgressTracker | None = None, single_file: Path | None = None) -> None`

遵循现有 `tasks/analyze.py` 模式：

1. 检查 `config.whisper.enabled` → 未启用时跳过（打印提示）
2. 导入 `faster_whisper` → `ImportError` 时打印友好报错："请先执行 `python main.py whisper install`"
3. 扫描 `compressed/`（含 `compressed/split/`）中的文件
4. **去重**：遍历所有文件，对每个调 `_resolve_original()` 拿到 `original_stem`，收集为唯一集合（set），确保同一原始视频只转录一次
5. 对每个 unique stem：
   - 检查 `output/transcripts/{stem}_transcript.json` 是否存在（`skip_existing`）
   - duration gate（`> max_analyze_duration_min` 跳过）
   - ffmpeg 提取音频到临时 `.wav`：
     ```
     ffmpeg -i <original_video> -vn -acodec pcm_s16le -ar 16000 -ac 1 <tmp.wav>
     ```
   - 临时文件使用 `tempfile.NamedTemporaryFile(delete=True)`（参考 B-003 教训，确保中断时自动清理）
   - `transcribe_audio()` → 写 transcript JSON
   - `tracker.update()` / `tracker.next()` / `_eta_line()` 进度

### `run_transcribe_one(config, video_path) -> dict`
单文件转录，供 UI rerun 使用。

### Transcript JSON 文件位置

```
output/
└── transcripts/
    ├── GL010683_transcript.json      ← 按原始 video stem 命名
    ├── GL010684_transcript.json
    └── ...
```

### Transcript JSON 格式

```json
{
  "source_video": "GL010683.MP4",
  "source_stem": "GL010683",
  "language": "zh",
  "model_size": "medium",
  "language_probability": 0.97,
  "audio_duration_sec": 120.5,
  "segments": [
    {
      "start": 0.0,
      "end": 2.5,
      "text": "今天天气真好",
      "avg_logprob": -0.12,
      "no_speech_prob": 0.02
    },
    {
      "start": 2.5,
      "end": 5.0,
      "text": "我们来到了埃菲尔铁塔",
      "avg_logprob": -0.08,
      "no_speech_prob": 0.01
    }
  ],
  "generated_at": "2026-06-14T10:30:00"
}
```

---

## 6. Plan Integration

### `plan_daily_vlog(clips, config, day_label, transcripts_map=...)`

`transcripts_map: dict[str, dict]` 由 `run_plan_vlog()` 预先加载：
- key = `source_stem`（如 `"GL010683"`）
- value = transcript JSON dict

在 `PLAN_PROMPT` 中新增变量 `{transcripts_json}`：
- 对每个 clip，查找匹配的 transcript
- 取 `use_timeline` 时间范围内的 segment
- 按 `avg_logprob` 降序取前 `max_segments_per_clip` 条
- 格式化为 JSON 字符串注入

Prompt 追加（在现有 `PLAN_PROMPT` 末尾）：

```
Additionally, here are the spoken content (transcript) segments for each clip.
Use them to determine which clips contain meaningful narration, understand the actual spoken context, and optimize the timing/ordering:

{transcripts_json}
```

**向后兼容**：`transcripts_map` 可空 / 无匹配 → 跳过注入，plan 行为与现在一致。
**空列表处理**：clip 的时间范围在 transcript 中无匹配 segments 时（如该时间段内无人说话），该 clip 不注入 transcript，不中断 plan 生成。

**Token 控制**：`max_segments_per_clip`（默认 5），防止 prompt 膨胀。

---

## 7. CLI

```bash
# 转录
python main.py transcribe                # 全量（skip_existing）
python main.py transcribe --force        # 覆盖
python main.py transcribe -i video.mp4   # 单文件

# Whisper 环境管理
python main.py whisper install           # pip install + 预下载模型
python main.py whisper check             # 检测 CUDA / faster-whisper / 模型
```

`transcribe` 复用 `_add_io_args()` 获取 `-i` 参数。
`whisper` 用子命令组实现（`subparsers`）。

`whisper install` 流程：
1. 尝试 `import faster_whisper`
2. 失败 → `pip install -r requirements-whisper.txt`
3. 检测 CUDA → 打印检测结果
4. 用配置的 `cache_dir` 预下载模型（`WhisperModel(model_name, download_root=...)`）
5. 打印完成

`whisper check` 流程：
1. 检测 `import faster_whisper`
2. 检测 `torch.cuda.is_available()`
3. 列出 `cache_dir` 中已缓存的模型
4. 打印状态表

---

## 8. UI

### 8.1 新增 Tab — "转录"

与"分析"、"口播"、"Plan" 并列，HTML 中添加 `#tab-transcript` 和对应的 tab 按钮。

**选中一条视频时**：
- 没有 transcript 文件 → 显示"暂无 transcript，请先运行转录步骤"
- 有 transcript → 显示片段列表

**显示逻辑（含 split 支持）**：

| 视频类型 | 显示哪些 segments | 时间显示 |
|----------|-------------------|----------|
| 原始视频（GL010683.MP4） | 全部 | 绝对时间（`00:10.0`） |
| 压缩完整版（001_GL010683.mp4） | 全部 | 绝对时间 |
| Split 段（001_GL010683_seg01.mp4） | 仅 `[offset_sec, offset_sec+duration)` 范围内 | 相对时间（`absolute - offset_sec`），标注 `+offset_sec` |

**每条 segment 卡片**：
```
[×] 00:10.0 → 00:12.5  今天天气真好  (avg_logprob: -0.12)
```
- 时间戳可点击 → `videoPlayer.currentTime = absolute_time`
- × 按钮 → 确认后从 JSON 移除该 segment 并保存
- 文本可 inline 编辑 → 保存按钮写回 JSON

**顶部信息栏**：`转录 — GL010683.MP4 | 语言: 中文 | 模型: medium | 置信度: 0.87`

### 8.2 Run Tab

`RUN_STEPS` 新增：
```javascript
{ key: 'transcribe', label: '语音转录', hint: 'Whisper ASR' }
```
默认排在 `compress` 之后、`analyze` 之前。

### 8.3 Sidebar

视频列表中，有 transcript 的视频项添加 CSS class `.has-transcript` 并在文件名后显示 `(T)` 角标（纯文本，符合 AGENTS.md 免 emoji 约定）。
视频名称下方显示"转录: zh / medium"（格式与"分析: 标题"一致）。

**无音轨视频**：`.lrv` 等代理文件可能不含音轨，ffmpeg 提取音频时静默失败 → 自动跳过该视频，进度中标记为"skip (no audio)"。

### 8.4 路由

| 路由 | 方法 | 用途 |
|------|------|------|
| `/api/transcripts` | GET | 获取指定视频的 transcript（加 `?source_stem=GL010683`） |
| `/api/transcripts` | PUT | 保存编辑后的 transcript（删除 segment、修改文本） |
| `/api/whisper/check` | GET | 返回环境检测结果（CUDA / 模型 / faster-whisper） |
| `/api/whisper/install` | POST | 后台运行 `whisper install`（可选，初始 UI 可省略） |

### 8.5 前端文件

| 文件 | 改动 |
|------|------|
| `index.html` | +`#tab-transcript` div + tab 按钮 |
| `state.js` | +`transcript` 字段 |
| `sidebar.js` | +角标 / +语言模型信息 |
| `editor.js` | +`renderTranscript()` + `renderActiveTab()` 分支 |
| `viewer.js` | +`seekToAbsolute(sec)` 供 transcript 点击调用 |
| `runner.js` | +`transcribe` step |

### 8.6 后端文件

| 文件 | 改动 |
|------|------|
| `server.py` | 注册 `/api/transcripts` 和 `/api/whisper/check` 路由 |
| `routes/transcripts.py`（新） | GET/PUT handler |
| `routes/whisper.py`（新） | check/install handler |

---

## 9. Dependency & Model Management

### 依赖文件

新建 `requirements-whisper.txt`（版本锁定）：
```
faster-whisper==1.1.0
ctranslate2>=4.0
```

同时在 `requirements.txt` 中添加一行注释引用，方便用户取消注释一键安装：
```
# whisper: 语音转录，取消下面注释以启用
# -r requirements-whisper.txt
```

`requirements-locked.txt` 不修改（whisper 依赖不影响核心工作流）。

### 模型缓存

默认位置：`<main.py 所在目录>/models/`
- Config 中 `whisper.cache_dir: null` 时自动解析为此路径
- `.gitignore` 加一行 `models/`
- `faster-whisper` 的 `download_root` 参数指向此目录

### `.gitignore`

追加：
```
models/
```

### Pipeline 检测

`run_pipeline_steps()` 中，如果 `"transcribe"` 在 steps 中但 `whisper.enabled == false` → 跳过并打印提示。
如果 `enabled == true` 但 `import faster_whisper` 失败 → raise `RuntimeError("请先执行 python main.py whisper install")`。

---

## 10. Testing

遵循项目现有 pytest 风格（mock `faster_whisper`，不跑真实模型）：

| 测试文件 | 测试内容 | Mock 策略 |
|----------|----------|-----------|
| `test_config.py` | `WhisperConfig` 加载/默认值/校验/枚举 | 无 |
| `test_transcribe.py` | `transcribe_audio()`: segment 解析、置信度过滤、`progress_callback` | `mock.patch("vlog_tool.transcribe.WhisperModel")` |
| `test_transcribe.py` | ffmpeg 音频提取命令行参数 | `mock.patch("subprocess.run")`（参考 `test_compress.py` 中已有的 ffmpeg mock 风格，适配 Windows subprocess 调用） |
| `test_tasks_transcribe.py` | `run_transcribe_all()`: skip_existing/duration gate/ETA/CSV | mock `transcribe_audio` 和 `_resolve_original` |
| `test_transcribe.py` | 无 `faster_whisper` 时 ImportError 报错 | mock `import` |
| `test_plan.py` | Plan prompt `{transcripts_json}` 注入 | mock transcript 文件 |
| `test_main.py` | CLI 子命令注册 | `pytest.param` |
| `test_routes_transcripts.py`（新） | `/api/transcripts` GET/PUT | mock handler |
| `test_routes_whisper.py`（新） | `/api/whisper/check` GET | mock handler |

---

## 11. Future Extension Points

- **逐视频语言覆盖**：`transcripts_meta.json` 中记录每个 video stem 的语言，UI 中下拉选择
- **Whisper 摘要注入 refine**（**明确不在 Phase 1 范围内**）：`whisper.refine_context: bool` + `refine_max_segments: 3`（config 已预留），摘要注入 `REFINE_TEXT_PROMPT` / `REFINE_SCRIPT_PROMPT`
- **云端 ASR 集成**：通过 provider 层实现 Gemini Audio / DeepSeek ASR，切到 `TaskName.TRANSCRIBE` + provider type `"gemini_audio"`
- **Whisper 缓存清理**：`python main.py whisper clean` 删除未使用的模型

---

## 12. Files Changed Checklist

| 文件 | 操作 |
|------|------|
| `vlog_tool/config.py` | +`WhisperConfig` dataclass + 枚举 + `AppConfig.whisper` 字段 + 解析 |
| `vlog_tool/transcribe.py` | **新文件**：`transcribe_audio()` + 模型缓存单例 |
| `vlog_tool/tasks/transcribe.py` | **新文件**：`run_transcribe_all()` + `run_transcribe_one()` |
| `vlog_tool/prompts.py` | +`TRANSCRIPT_CONTEXT` prompt 片段 |
| `vlog_tool/analyze.py` | `plan_daily_vlog()` 接收 `transcripts_map` + 注入 `{transcripts_json}` |
| `vlog_tool/tasks/plan.py` | `run_plan_vlog()` 加载 transcripts 并传递 |
| `vlog_tool/pipeline.py` | +`"transcribe"` step 注册 + 检测逻辑 |
| `main.py` | +`transcribe` / `whisper` 子命令 |
| `config.example.yaml` | +`whisper:` 节（注释枚举选项） |
| `.gitignore` | +`models/` |
| `requirements-whisper.txt` | **新文件** |
| `requirements.txt` | +注释引用 `requirements-whisper.txt` |
| `requirements-locked.txt` | 不修改 |
| `vlog_tool/ui/static/index.html` | +tab 按钮 + `#tab-transcript` |
| `vlog_tool/ui/static/src/state.js` | +`transcript` 字段 |
| `vlog_tool/ui/static/src/sidebar.js` | +角标 + 转录信息 |
| `vlog_tool/ui/static/src/editor.js` | +`renderTranscript()` |
| `vlog_tool/ui/static/src/viewer.js` | +`seekToAbsolute()` |
| `vlog_tool/ui/static/src/runner.js` | +`transcribe` step |
| `vlog_tool/ui/routes/transcripts.py` | **新文件**：GET/PUT |
| `vlog_tool/ui/routes/whisper.py` | **新文件**：check/install |
| `vlog_tool/ui/server.py` | 注册新路由 |
| `vlog_tool/tests/test_config.py` | +`WhisperConfig` 测试 |
| `vlog_tool/tests/test_transcribe.py` | **新文件** |
| `vlog_tool/tests/test_tasks_transcribe.py` | **新文件** |
| `vlog_tool/tests/test_routes_transcripts.py` | **新文件** |
| `vlog_tool/tests/test_routes_whisper.py` | **新文件** |
| `docs/superpowers/specs/2026-06-14-whisper-transcription-design.md` | 本文档 |
| `README.md` / `README.en.md` | +Whisper 用法说明 |
| `AGENTS.md` | +Whisper 相关记录 |

---

*— END —*
