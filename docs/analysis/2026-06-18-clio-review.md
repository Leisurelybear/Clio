# vlog-editing-helper 代码审查报告

> 审查日期：2026-06-18  
> 覆盖范围：全部 Python 源码 + JS 前端 + 配置体系  
> 当前状态：架构清晰、核心机制完善，距离「开箱即用」还有若干关键缺口

---

## 一、总体评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | ⭐⭐⭐⭐ | 任务拆分清晰，pipeline 可组合，AI 提供商抽象优雅 |
| 稳定性 | ⭐⭐⭐ | 原子写入已覆盖，但 cut.py 仍有遗漏；ffmpeg 进程管理有隐患 |
| 可用性 | ⭐⭐⭐ | 取消机制已加入，但 UI 体验仍较粗糙 |
| 测试覆盖 | ⭐⭐⭐⭐ | 覆盖范围广，但 conftest 全局缓存污染问题待修 |
| 核心功能完整度 | ⭐⭐ | **CapCut/剪映草稿导出完全缺失**，是最大功能空白 |

---

## 二、🔴 必须修复（影响基本可用）

### P0-1：`cut.py` 写文件未使用原子操作

**位置**：`clio/tasks/cut.py:156, 191`

```python
# 直接写，崩溃会留下损坏文件
dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

全项目其他地方已统一用 `write_json_atomic` / `write_text_atomic`，唯独 `cut.py` 遗漏了。裁剪中途崩溃会留下内容不完整的 JSON，再次运行时 `skip_existing` 逻辑会认为已完成而跳过，导致数据静默损坏。

**修复**：
```python
from vlog_tool.utils import write_json_atomic, write_text_atomic

write_json_atomic(dst, data)
write_text_atomic(manifest_path, "\n".join(lines) + "\n")
```

---

### P0-2：`server.py` project.json 迁移写入非原子

**位置**：`clio/ui/server.py:91`

```python
project_path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
```

服务器启动时执行迁移，如果此刻进程被 kill，`project.json` 会损坏，下次启动后找不到项目。改用 `write_json_atomic` 即可修复。

---

### P0-3：`_provider_cache` 全局变量导致测试互相污染

**位置**：`clio/ai/factory.py`、`clio/tests/conftest.py`

```python
# factory.py — 进程级全局缓存
_provider_cache: dict[tuple, TextAIProvider] = {}
```

`conftest.py` 没有在每个测试前后自动 clear 缓存，前面测试 mock 的 provider 会被后面测试复用，导致偶发性测试失败（在 CI 环境下顺序不同时尤其明显）。

**修复**：
```python
# conftest.py
@pytest.fixture(autouse=True)
def clear_provider_cache():
    from vlog_tool.ai.factory import _clear_provider_cache
    _clear_provider_cache()
    yield
    _clear_provider_cache()
```

---

### P0-4：`run_plan_vlog` 的 transcripts 加载忽略 `use_transcripts` 配置

**位置**：`clio/tasks/plan.py:52-62`

```python
if trans_dir.is_dir() and config.whisper.enabled:  # ← 只检查 enabled
    for tf in sorted(trans_dir.glob("*_transcript.json")):
        ...
```

`config.plan.use_transcripts` 是用户在 UI 上的运行时开关，但这里只判断了 `whisper.enabled`，导致用户取消勾选「使用语音转录优化剪辑规划」后实际上不生效。

**修复**：条件改为 `config.whisper.enabled and config.plan.use_transcripts`

---

## 三、🟠 健壮性问题（影响偶发场景）

### R-1：AI 返回内容缺乏结构校验

**位置**：`clio/tasks/analyze.py`、`clio/tasks/plan.py`

AI 返回的 JSON 直接被 `data.get("xxx")` 取值，缺少字段时静默返回 `None`/空字符串，不报错也不告警。如果 Gemini 返回了截断或格式变更的内容，后续步骤会用空数据生成规划，难以排查。

**建议**：在写入磁盘前做最小字段校验，缺关键字段时打印告警并跳过（而不是静默写入空数据）：
```python
REQUIRED_FIELDS = {"title", "summary", "timeline", "highlights"}
missing = REQUIRED_FIELDS - set(analysis.keys())
if missing:
    print(f"  [警告] {compressed.name} AI 返回缺少字段: {missing}，已用空值补全")
    for f in missing:
        analysis.setdefault(f, "" if f != "timeline" else [])
```

---

### R-2：`compress_video` 音频码率使用魔法数字

**位置**：`clio/compress.py:49`

```python
target_bits -= int(128_000 * duration * 1.05)  # 预留 128kbps 音频 + 5% 余量
```

当 `remove_audio=False`（用户自定义配置）时，固定假设 128kbps 与实际 AAC 编码（96-256kbps 不等）可能偏差很大，导致压缩后文件大小超出目标值较多。可用 ffprobe 探测音频流实际码率替代。

---

### R-3：`_resolve_original` 使用 `rglob` 递归扫描效率低

**位置**：`clio/tasks/analyze.py:35-42`

每个视频分析前都做一次全目录递归 `rglob`，素材目录有几百个文件时（尤其非递归模式）会产生大量 IO，建议在 `run_analyze_all` 开始时一次性建立 `{stem: Path}` 映射缓存。

---

### R-4：`run_cut_all` 缺少 `cancel_event` 支持

`run_compress_all` 和 `run_transcribe_all` 都已接入 `cancel_event`，但 `run_cut_all` 没有，用户点击取消后裁剪步骤无法中断。

---

## 四、🟡 性能问题

### Perf-1：AI 分析和文案生成全部串行

**位置**：`clio/tasks/analyze.py`、`clio/tasks/scripts.py`

每个视频的 AI 分析等待上传+处理+下载，整个过程完全串行。20 个 GoPro 片段，每个处理 30 秒，就是 10 分钟等待。

**建议**：用 `ThreadPoolExecutor(max_workers=3)` 并发，注意 Gemini 的 RPM 限制（`ratelimit.py` 已有 `RateLimiter`，可直接复用）：
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=config.ai.providers[provider].requests_per_minute // 20 or 3) as pool:
    futures = {pool.submit(_analyze_one, item): item for item in items}
    for fut in as_completed(futures):
        records.append(fut.result())
```

---

### Perf-2：进度文件每次 `mark()` 都刷一次磁盘

**位置**：`clio/processing_state.py`

`ProcessingState.mark()` 每次都同步 `_flush()`，并发化后会成为锁争用热点。可改为批量写入（`mark()` 只更新内存，启动一个定期 flush 线程），或者至少在串行场景下每 N 次 flush 一次。

---

## 五、🔵 体验与「开箱即用」差距

### UX-1：**CapCut/剪映草稿导出完全缺失**（最大功能空白）

整个工具链的终点应该是「点一下就能在剪映里剪」，但目前 `cut` 步骤只输出 mp4 片段，用户还需要手动在剪映里重新排列素材、对齐时间轴，等于完成了 70% 的工作但最后 30% 仍是手工。

ROADMAP 已有 R-002 占位，但没有实现。这是距离「zero-editing」目标最大的功能缺口，建议优先实现：
- 导出 `draft_content.json`（剪映草稿格式）
- 包含素材路径、时间轴、字幕文本

---

### UX-2：首次配置门槛高

用户需要手动编辑 `config.yaml`，填写正确的目录路径和 API Key，没有任何引导。建议 Web UI 增加首次启动向导（Setup Wizard）：
1. 输入视频目录 → 自动探测 ffmpeg → 填写 API Key → 测试连接
2. 向导完成后自动写入 `config.yaml`，消除手动编辑需求

---

### UX-3：`ANALYZE_PROMPT` 硬编码「旅行 vlog」

**位置**：`clio/prompts.py`

所有 prompt 都预设了旅行语境（`旅行 vlog 口播文案写手`、`旅行 vlog 剪辑策划`），用于美食/日常/运动类内容时 AI 输出明显偏离。

建议将 prompt 移至 `templates/prompts/`，`config.yaml` 增加 `ai.vlog_type` 参数自动选择模板。

---

### UX-4：缺少 macOS/Linux 安装脚本

`setup.ps1` 只支持 Windows，macOS/Linux 用户需要手动安装 ffmpeg、创建 venv、安装依赖。对目标受众（GoPro 用户）来说这是不小的门槛。

---

### UX-5：运行状态切换 tab 后丢失

切换到其他 tab 再切回 run tab，进度信息会被重置，pollRunStatus 在后台静默继续但 UI 不显示。`state.runStatus` 应缓存最新状态，切回 run tab 时立即恢复渲染。

---

### UX-6：`TRANSCRIPT_CONTEXT` prompt 使用英文混杂中文

**位置**：`clio/prompts.py`

全项目其他 prompt 均为中文，唯独 `TRANSCRIPT_CONTEXT` 是英文，语言混杂可能影响 AI 的输出一致性（Gemini 可能开始用英文回复）。

---

## 六、⚪ 代码质量（影响长期维护性）

### Q-1：compress 循环的 closure 陷阱（潜在并发 bug）

**位置**：`clio/tasks/compress.py`

```python
for i, (original, source) in enumerate(items, start=1):
    def _on_progress(_sec, total_dur):
        tracker.update(current=i, ...)  # i 是 late binding
```

串行执行时无问题，一旦并发化，所有 `_on_progress` 都会用循环末尾的 `i` 值，进度显示会乱。用工厂函数绑定：`def _make_cb(i): return lambda s, d: tracker.update(current=i, ...)`

---

### Q-2：`run_pipeline_steps` 的 `cancel_event` 仅传给部分步骤

**位置**：`clio/pipeline.py:84`

```python
if cancel_event and step in ("compress", "transcribe"):
    kwargs["cancel_event"] = cancel_event
```

`analyze`、`voiceover`、`label` 不传 `cancel_event`，这些步骤期间取消请求会被忽略，必须等当前步骤完成才生效。应将 `cancel_event` 传给所有支持它的步骤。

---

### Q-3：`Handler` class 用类变量共享线程状态，多项目并发时不安全

**位置**：`clio/ui/server.py`

```python
class Handler(BaseHTTPRequestHandler):
    _run_lock = threading.Lock()       # 类级别
    _run_thread = None                 # 共享
    _cancel_event = threading.Event()  # 共享
```

如果将来支持多项目同时运行，这个设计会使所有项目共用同一把锁和同一个线程槽。建议改为实例变量，或引入 per-project 的运行状态管理器。

---

### Q-4：`sidebar.js` 685 行，`editor.js` 619 行，单文件过大

前端没有组件化，两个最大的文件都超过 600 行，函数间数据流靠全局 `state` 对象传递，难以追踪副作用。这是后面「要不要用 React 重写」讨论的核心背景。

---

## 七、关于用 React 重写 UI —— 有没有必要？

### 简短结论：**有必要，但不要现在做**

**支持 React 重写的理由：**

1. **现有 vanilla JS 维护成本正在上升**：`sidebar.js`（685 行）和 `editor.js`（619 行）都通过直接操作 DOM + 全局 `state` 对象共享状态，随着功能增加，追踪某个状态变化来自哪里越来越难。
2. **即将要加的功能天然适合组件化**：CapCut 导出预览、多天规划、视频列表+播放器联动，这些都是有复杂状态的 UI，用 React 写起来比手动 `innerHTML` 清晰得多。
3. **打包后体积可控**：Vite + React 打包出来的产物仍然可以由 Python http.server 静态托管，不需要改 Python 后端。

**反对现在就动手的理由：**

1. **后端还有更多优先级更高的工作**：P0 bug（cut.py 非原子写、provider cache 污染）、CapCut 导出、取消机制完善，这些直接影响核心功能，比 UI 框架迁移更重要。
2. **重写期间功能开发会停滞**：React 迁移是个「全或无」的事，中间状态（混用 vanilla + React）比纯 vanilla 更难维护。
3. **现有后端 API 完全支持 React**：REST + JSON 结构已经很干净，切换前端框架不需要动后端一行代码，所以不是现在就必须做的耦合问题。

**建议时间节点**：

| 阶段 | 工作 |
|------|------|
| 当前（阶段一） | 修完 P0 bug，做好原子写入和测试修复 |
| 阶段二 | 实现 CapCut 导出 + 稳定 cut 流程 |
| **阶段三** | **用 React 重写 UI**，此时功能集稳定，不会边写边改 API |

如果那时候动手，推荐技术栈：**Vite + React + Zustand（状态管理）**，不引入 TypeScript（保持简单），继续用现有 REST API，不换 WebSocket（除非实时日志有需求）。

---

## 附：现有亮点（不要动）

| 机制 | 说明 |
|------|------|
| `write_json_atomic` / `write_text_atomic` | 原子写入覆盖全项目（cut.py 修完后完整），崩溃安全 |
| `ProcessingState` 状态矩阵 | 文件级 × 步骤级持久化，断点续跑的基础，设计精良 |
| `with_retry` 指数退避 | 正确处理 Gemini 429 / ServerError，不需要改动 |
| `ai.context` 注入机制 | 行程背景前置到所有 prompt，有效减少 AI 误判 |
| AI Provider 抽象 | `TextAIProvider` + factory，任务与厂商完全解耦 |
| `python main.py check` | 环境检查 CLI 覆盖全面，用户体验好 |
| `cancel_event` 机制 | 已正确接入 compress / transcribe，pipeline 层有检查点 |
