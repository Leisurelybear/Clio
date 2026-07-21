# vlog-editing-helper 全面代码审查报告

> 基于仓库 `Leisurelybear/vlog-editing-helper` 最新代码（截至 2026-06-28）
> 覆盖最近两天约 40 次提交（从 `f299f5a` 到 `dd494d6`）

---

## 目录

1. [Bug 汇总](#1-bug-汇总)
2. [功能缺陷](#2-功能缺陷)
3. [架构问题](#3-架构问题)
4. [可优化点](#4-可优化点)
5. [可新增功能](#5-可新增功能)
6. [可重构模块](#6-可重构模块)
7. [总结优先级表](#7-总结优先级表)

---

## 1. Bug 汇总

### BUG-001 ⚠️ `handle_post_rerun` 的 `analyze` / `voiceover` lambda 缺少 `cancel_event` 传递

**文件**: `clio/ui/routes/run.py`，第 192–193 行

**现象**: 用户在 UI 中点击"取消"后，rerun 的 compress 步骤会响应取消，但 analyze 和 voiceover 步骤对取消信号无感知，会继续跑完整个 AI 调用。

**根因**:

```python
# 当前代码（有问题）
("analyze", lambda: run_analyze_all(cfg, tracker=tracker, single_file=original_video), "AI 分析"),
("voiceover", lambda: run_generate_scripts(cfg, tracker=tracker, single_file=texts_json), "生成口播"),
```

`run_analyze_all` 和 `run_generate_scripts` 都接受 `cancel_event` 参数，但 rerun 的 lambda 没有传入。

**修复方案**:

```python
# 修复后
(
    "analyze",
    lambda: run_analyze_all(
        cfg, tracker=tracker, single_file=original_video, cancel_event=cancel_event
    ),
    "AI 分析",
),
(
    "voiceover",
    lambda: run_generate_scripts(
        cfg, tracker=tracker, single_file=texts_json, cancel_event=cancel_event
    ),
    "生成口播",
),
```

---

### BUG-002 ⚠️ `generate_voiceover()` 不支持 `cancel_event`

**文件**: `clio/analyze.py`，第 199 行；`clio/tasks/scripts.py`，第 71 行

**现象**: 即使上层已检查 `cancel_event.is_set()`，一旦 AI 调用开始，整个 voiceover 生成无法被中途取消（Gemini 文本调用无超时中断点）。

**根因**: `generate_voiceover` 签名为 `(clip_data, template, config, token_store=None)`，没有 `cancel_event` 参数，且内部不做取消检查。

**修复方案**:

```python
# analyze.py
def generate_voiceover(
    clip_data: dict,
    template: str,
    config: AppConfig,
    token_store=None,
    cancel_event: threading.Event | None = None,  # 新增
) -> dict:
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("voiceover 被用户取消")
    provider, model = get_task_provider(config, TaskName.VOICEOVER)
    # ... 其余逻辑不变，AI 调用时透传 cancel_event
```

```python
# tasks/scripts.py 调用处
script = generate_voiceover(data, template, config, token_store=token_store, cancel_event=cancel_event)
```

---

### BUG-003 ⚠️ `RateLimiter.__enter__` 存在日志状态竞态

**文件**: `clio/ratelimit.py`，第 20–28 行

**现象**: 在多线程场景下（`max_workers > 1`），`_logged` 标志在锁释放后立即被重置为 `False`，导致同批次的多个线程可能重复打印限流日志。

**根因**:

```python
with self._lock:
    if now < self._next_at:
        wait = self._next_at - now
        if not self._logged:
            print(...)
            self._logged = True
    self._next_at = time.monotonic() + self._interval
    self._logged = False  # ← 锁内立即重置，下一个线程进锁后 _logged 已是 False
```

实际上 `acquire()` 方法（推荐多线程用法）已正确处理此问题。`__enter__` 方式应只在单线程场景使用，但没有文档说明。

**修复方案（选一）**:
- 在 `__enter__` 的 docstring 注明"仅适用于单线程场景，多线程请用 `acquire()`"
- 或直接废弃 `__enter__`/`__exit__`，统一改用 `acquire()`

---

### BUG-004 ⚠️ Gemini 代理测试在 SOCKS5 URL 下失败（依赖未声明）

**文件**: `clio/tests/test_ai_gemini.py`，第 33 行

**现象**: `test_creates_client_with_proxy` 在 CI 中失败，报 `ImportError: httpx[socks]` 未安装。

**根因**: 测试使用了 `socks5://127.0.0.1:1080` 作为代理 URL，但 `requirements.txt` 中只声明了 `httpx`，而 SOCKS5 支持需要 `httpx[socks]`（即 `socksio` 包）。

**修复方案（二选一）**:

```txt
# requirements.txt 添加可选依赖
httpx[socks]>=0.27
```

或将测试中的代理 URL 改为 HTTP：

```python
# conftest
@pytest.fixture
def proxy_enabled():
    return ProxyConfig(enabled=True, url="http://127.0.0.1:1080")
```

---

### BUG-005 🔶 `jianying.py` 导出时留有大量 `[debug]` print 语句

**文件**: `clio/export/jianying.py`，第 55、61、65、72、75、77、84、339、341 行

**现象**: 每次调用 `/api/export` 或 CLI `export`，服务端控制台会输出大量 `[debug]` 日志，包括完整的 `texts_dir` 路径、所有文件列表和索引映射，不适合生产环境。

**修复方案**: 将调试 print 替换为 `logging.debug()`，或用 `config.ai.debug_print_prompt` 类似的开关控制：

```python
import logging
logger = logging.getLogger("vlog_tool.export.jianying")

# 替换所有 print(f"  [debug] ...")
logger.debug("texts_dir=%s, index_to_source=%s", texts_dir, index_to_source)
```

---

### BUG-006 🔶 `VideoMeta.read()` 数据层次结构脆弱（但当前正确）

**文件**: `clio/vmeta.py`，第 80–97 行

**现象**: 非 bug，但有潜在风险。`_meta_to_dict` 把字段分成两层——`"data"` 子对象包含路径/分段信息，而 `source_modifyTime` 等在顶层。`read()` 使用 `data = raw.get("data", raw)` 做 fallback，导致向后兼容逻辑隐式依赖 fallback 路径。

**建议**: 在 `write()` 时加入 `schema_version` 字段（已有 `VMETA_VERSION = 1`），在 `read()` 中显式按 version 区分解析路径，避免 `get("data", raw)` 的隐式 fallback 被误用。

---

### BUG-007 ✅ `R-006d` 中记录的已知 UI Bug：切换 source 时 plan 视图播放器不自动跳转

**根因**: `playVideoSegment()` 设置了播放器 src 但从未更新 `state.currentVideo`。之后 `setSource()` 用 `state.currentVideo` 匹配新旧视频时得到 null。

**修复**: `playVideoSegment()` 添加 `state.currentVideo = file`（commit `822f72c`）。

---

## 2. 功能缺陷

### FD-001 🚨 剪映导出 canvas 写死为 1920×1080，不支持竖屏 / 其他比例

**文件**: `clio/export/jianying.py`，第 357–360 行

```python
"canvas_config": {
    "width": 1920,
    "height": 1080,
    "ratio": 1.7777777777777777,
},
```

手机拍摄的竖屏素材（9:16）导入剪映后会被错误地放入横屏画布，需要手动调整。

**修复方案**: 在 `export_plan_to_jianying` 加 `aspect_ratio` 参数，并在 `AppConfig` 的 `ExportConfig`（或 plan 数据）中存储目标比例：

```python
CANVAS_PRESETS = {
    "16:9":  {"width": 1920, "height": 1080, "ratio": 16/9},
    "9:16":  {"width": 1080, "height": 1920, "ratio": 9/16},
    "1:1":   {"width": 1080, "height": 1080, "ratio": 1.0},
}
```

---

### FD-002 🚨 `transcripts_dir` 不是 `AppConfig` 的 property，路径逻辑分散

**现象**: `scripts_dir`、`texts_dir`、`plans_dir`、`compressed_dir` 都是 `AppConfig` 的 `@property`，但 `transcripts_dir` 没有，各处自行拼 `config.paths.output_dir / config.whisper.transcripts_subdir`，有 4 处重复（`transcripts.py`、`videos.py`、`tasks/transcribe.py` x2）。

**修复方案**（一行）:

```python
# clio/config/models.py — AppConfig 中添加
@property
def transcripts_dir(self) -> Path:
    return self.paths.output_dir / self.whisper.transcripts_subdir
```

---

### FD-003 🚨 voiceover / plan 步骤的 AI 调用是**串行**的，无法利用 `max_workers`

**文件**: `clio/tasks/scripts.py`，`clio/tasks/plan.py`

**现象**: `run_generate_scripts` 和 `run_plan_vlog` 中的 AI 调用全部串行 `for` 循环。只有 `run_analyze_all` 有 `ThreadPoolExecutor`，voiceover 处理 20 个视频比 analyze 慢得多。

**修复方案**: 参考 `analyze.py` 的批处理实现，对 `run_generate_scripts` 增加 `ThreadPoolExecutor` 支持：

```python
# tasks/scripts.py
with ThreadPoolExecutor(max_workers=max_workers) as pool:
    futures = {pool.submit(_process_one_script, ...): json_file for json_file in input_files}
    for future in as_completed(futures):
        ...
```

注意：需要配合 RateLimiter 的 `acquire()` 方法（已有），且需要线程安全的 `error_count` 累计。

---

### FD-004 🔶 剪映导出缺少 UI 触发入口 / 导出结果路径没有在前端展示

**文件**: `clio/ui/routes/export.py`、`clio/ui/static/src/`

**现象**: 后端 `/api/export` 已实现，但前端 plan 视图中没有"导出到剪映"按钮。用户必须通过 CLI `python main.py export` 触发，这是零剪辑目标的最后一步，却没有 UI 入口。

**修复方案**:
1. 在 plan 视图右上角加"导出剪映草稿"按钮
2. 导出后展示 `output/export/` 目录路径，并提供"在文件管理器中打开"的提示

---

### FD-005 🔶 `auto_reindex_if_needed` 在服务启动时调用 `os.system("cls/clear")` 清屏

**文件**: `clio/tasks/reindex.py`

**现象**: 服务端（`python main.py serve`）启动时如果需要 reindex，会直接清空终端界面，用户可能丢失启动日志。在 CI/CD 环境或管道输出中尤其有问题。

**修复方案**: 改为直接打印分隔线，不调用 `os.system("clear")`：

```python
# 替换 os.system("cls" if os.name == "nt" else "clear")
print("\n" + "=" * 60)
print("  [reindex] 检测到压缩文件缺少 sidecar，正在重建...")
print("=" * 60)
```

---

### FD-006 🔶 `whisper.enabled: true` 但用户未安装 faster-whisper 时，pipeline 报错不友好

**文件**: `clio/tasks/transcribe.py`

**现象**: `whisper.enabled` 默认为 `True`，新用户跑 `analyze` 或 `run` 时若未安装 faster-whisper，`transcribe` 步骤会抛出 `ModuleNotFoundError`，错误信息不如 `run.py` 中 `check_whisper()` 的提示清晰。

**修复方案**: 在 `run_transcribe_all` 入口处提前检查：

```python
from vlog_tool.transcribe import check_whisper
if not check_whisper():
    if tracker:
        tracker.log("⚠ faster-whisper 未安装，跳过转录步骤。执行: python main.py whisper install")
    print("[跳过] whisper 未安装")
    return []
```

---

## 3. 架构问题

### ARCH-001 🚨 `server.py` 中路由分发是手写的 `if path == ...` 链，缺少框架级路由

**文件**: `clio/ui/server.py`，`do_GET`/`do_PUT`/`do_POST`

**现象**: 目前有约 35 个 GET、12 个 PUT、16 个 POST 端点，全部用 `if path == "/api/xxx":` 线性匹配。每新增路由都要修改 3 个方法，且无法做路径参数（`/api/vmeta/<stem>` 是用 `startswith` + 切片实现的，很脆弱）。

**当前影响**: 已有 `/api/vmeta/<stem>` 这种路径参数端点，未来扩展更多端点时维护成本急剧上升。

**重构方案**（保持零依赖原则）:

```python
# 用 (method, pattern) 注册表替换 if 链
from __future__ import annotations
import re
from typing import Callable

RouteHandler = Callable[..., None]

@dataclass
class _Route:
    method: str
    pattern: re.Pattern
    handler: RouteHandler
    param_names: list[str]

class Router:
    def __init__(self):
        self._routes: list[_Route] = []

    def add(self, method: str, path: str, handler: RouteHandler) -> None:
        param_names = re.findall(r"<(\w+)>", path)
        pattern = re.compile("^" + re.sub(r"<\w+>", r"([^/]+)", path) + "$")
        self._routes.append(_Route(method, pattern, handler, param_names))

    def dispatch(self, method: str, path: str) -> tuple[RouteHandler, dict] | None:
        for route in self._routes:
            if route.method != method:
                continue
            m = route.pattern.match(path)
            if m:
                return route.handler, dict(zip(route.param_names, m.groups()))
        return None
```

无需引入 Flask/FastAPI，仍使用 `http.server`，但路由注册整洁可维护。

---

### ARCH-002 🔶 `AppConfig` 没有 `ExportConfig` — 导出参数（画布比例、ffprobe 等）无处配置

**现象**: `export_plan_to_jianying` 接受 `ffprobe: str | None = None`，但 `AppConfig` 里没有导出专用的配置节，导致导出行为无法通过 `config.yaml` 控制（宽高、帧率、是否包含 voiceover 文字轨等）。

**修复方案**: 在 `models.py` 添加：

```python
@dataclass
class ExportConfig:
    canvas_ratio: str = "16:9"     # "16:9" | "9:16" | "1:1"
    fps: int = 30
    include_text_track: bool = True
    output_subdir: str = "export"

# AppConfig 中添加
export: ExportConfig = field(default_factory=ExportConfig)
```

---

### ARCH-003 🔶 Phase 6（全局 vs 项目配置分离）的设计目标与当前实现存在根本冲突

**现象**: 当前 `AppConfig` 把 `ai.providers`（API keys，应为全局）和 `compress`/`plan` 参数（应为项目级）放在同一个 dataclass 里，`ConfigCache` 把它们合并加载。ROADMAP Phase 6 要分离，但分离意味着所有使用 `config.xxx` 的地方都需要重新区分来源。

**建议**: 在正式实施 Phase 6 之前，先完成一个"标注层"——在 `models.py` 中用注释或 `field(metadata={"scope": "global"})` 标记每个字段属于哪一层，避免 Phase 6 时遗漏。

---

### ARCH-004 🔶 `ProcessingState` 每次 `mark()` 都完整写入磁盘（`_flush()`），高频调用时 I/O 浪费

**文件**: `clio/processing_state.py`

**现象**: 每标记一个文件的一个步骤，就把整个状态矩阵序列化为 JSON 并 `tmp.replace()`。100 个视频 × 6 步骤 = 600 次写磁盘。

**修复方案**: 引入写入防抖（debounce），或改为异步批量写：

```python
def mark(self, file_stem: str, step: str, status: str) -> None:
    with self._lock:
        # 更新内存状态
        ...
        self._dirty = True
    # 异步 flush（每 1s 写一次）
    self._schedule_flush()
```

或最简单的：每 N 次 mark 才写一次：

```python
self._pending += 1
if self._pending >= 5:
    self._flush()
    self._pending = 0
```

---

## 4. 可优化点

### OPT-001 `_build_stem_to_path` 重复建立于每次 `run_analyze_all` 调用但 rerun 中没有复用

**文件**: `clio/tasks/analyze.py`，第 33 行

当前 `run_analyze_all` 内部会建立 `stem_cache`，但 `single_file` 路径的调用（rerun）每次都重新 rglob，可以共用同一个 cache 对象。影响不大，但改起来简单。

---

### OPT-002 `ProgressTracker.logs` 列表无上限，长时间运行会无限增长

**文件**: `clio/progress.py`

每次 `tracker.log()` 都追加到 `self._data["logs"]`，没有最大条目限制。处理数百个视频时 `.progress.json` 会变得很大，影响轮询延迟。

**修复方案**:

```python
MAX_LOGS = 200

def log(self, message: str) -> None:
    with self._lock:
        self._data["logs"].append(message)
        if len(self._data["logs"]) > MAX_LOGS:
            self._data["logs"] = self._data["logs"][-MAX_LOGS:]
        self._flush()
```

---

### OPT-003 `_quick_hash` 只读 1MB，但 `verify` 字段在读取时从不校验

**文件**: `clio/vmeta.py`

`VideoMeta.build()` 计算了 `verify`（SHA256 前 1MB），但 `VideoMeta.read()` 之后从未调用过校验逻辑。这个字段目前是"写了不用"的状态。

**建议**: 要么在 `is_stale()` 中加上哈希校验（可选，开销较大），要么删掉 `verify` 字段并在注释中记录"预留给未来完整性校验"。

---

### OPT-004 `server.py` 中 `do_PUT` 对所有路由都解析 JSON，但某些 PUT 不需要 body

**文件**: `clio/ui/server.py`，第 235–242 行

所有 PUT 请求都强制解析 body 为 JSON dict，如果以后有 PUT 需要接收二进制流，此处需要重构。现在影响不大，但路由注册方案（ARCH-001）实现后可以在路由级别配置 body 解析策略。

---

### OPT-005 `split_video` 结果存 `_split_manifest.json`，但 `_build_split_info` 每次重新读取

**文件**: `clio/tasks/compress.py`，`_build_split_info` 函数

每次写 `.vmeta` 都要重新读 `_split_manifest.json`。在同一个 `run_compress_all` 调用里，可以在开始时一次性加载所有 manifest 到内存，避免重复 I/O。

---

### OPT-006 `editor.js`（1228 行）是前端最大的单文件，已超出合理阅读范围

**文件**: `clio/ui/static/src/editor.js`

ROADMAP Phase 5 已列为待办项，建议拆分为：
- `editor-texts.js` — 文本/分析结果编辑
- `editor-voiceover.js` — 口播文案编辑
- `editor-plan.js` — plan 视图（目前内嵌在 editor.js 中）
- `editor-timeline.js` — 时间轴片段预览

每个模块 200–400 行，可读性大幅提升。

---

## 5. 可新增功能

### NEW-001 🔥 批量导出 + 自动复制到剪映草稿目录

**背景**: 剪映专业版草稿目录在 `~/Movies/JianyingPro/User Data/Projects/`（macOS）或 `%USERPROFILE%\AppData\Local\JianyingPro\User Data\Projects\`（Windows）。

**建议**: 在 `ExportConfig` 中加 `jianying_draft_dir`，导出后自动拷贝 `draft_content.json` 到对应目录，用户打开剪映即可直接看到草稿，无需手动拷贝。这是"零剪辑"目标的最后一公里。

```yaml
# config.yaml
export:
  jianying_draft_dir: "~/Movies/JianyingPro/User Data/Projects/"
  auto_copy_draft: true
```

---

### NEW-002 🔥 `vmeta` 完整性校验 CLI 命令

**背景**: 现有 `reindex` 命令重建 sidecar，但没有"verify"命令让用户主动检查哪些压缩文件与原始文件已不一致（源文件被替换、SD 卡格式化等）。

**建议**: 添加 `python main.py verify` 命令：

```
📂 GL010683.mp4  ✓ OK (source matches vmeta)
📂 GL010695.mp4  ⚠ STALE (source mtime changed, re-compress recommended)
📂 GL010701.mp4  ✗ MISSING (compressed file not found)
```

实现：遍历 `.vindex`，调用 `VideoIndex.is_stale()` 和 `VideoMeta` 的 `_quick_hash` 校验。

---

### NEW-003 🔥 AI 分析结果质量评分 + 自动重试低质量输出

**背景**: 有时 Gemini 返回的 `timeline` 为空、`title` 过短，用户需要手动触发 rerun。

**建议**: 在 `_validate_analysis` 后加质量评分逻辑：

```python
def _quality_score(data: dict) -> float:
    score = 0.0
    if len(data.get("timeline", [])) >= 3: score += 0.4
    if len(data.get("title", "")) >= 5: score += 0.2
    if len(data.get("summary", "")) >= 20: score += 0.3
    if data.get("location", "未知") != "未知": score += 0.1
    return score
```

若 `score < 0.5`，自动重试一次（已有 `retry_attempts` 机制，可复用）。

---

### NEW-004 多 day 聚合 plan + 跨天剪辑序列生成

**背景**: 当前 `plan` 每次只生成 `day1_plan.json`，多天 vlog 需要手动分目录。

**建议**: 添加 `python main.py plan --all-days` 命令，自动扫描 `texts/` 中带有日期/day 标签的文件，生成 `trip_plan.json`（多天聚合），包含建议的跨天转场。

---

### NEW-005 WebSocket 替换 2s 轮询进度更新

**背景**: 当前 `runner.js` 每 2 秒 `GET /api/run/status`，在处理速度快的场景下（label、cut 步骤）进度反馈有 2s 延迟，且每个连接客户端都独立轮询。

**建议**: Python 标准库 `http.server` 不支持 WebSocket，但可以用 **Server-Sent Events (SSE)**——纯 HTTP，无需额外库：

```python
# 新增 GET /api/run/stream
def handle_get_run_stream(handler, qs):
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    while True:
        data = read_progress_file(...)
        handler.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
        handler.wfile.flush()
        if data["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(0.5)
```

前端改为 `new EventSource("/api/run/stream")` 即可，延迟从 2s 降到 500ms，且服务端可主动 push。

---

### NEW-006 `clip_record` 的 `duration_sec` 写入 CSV 但没有展示在 UI 中

**背景**: `summary.csv` 包含每个视频时长，但 UI 视频列表没有显示，用户无法快速评估哪些视频素材太长/太短。

**建议**: 在 `/api/videos` 返回中加入 `duration_sec` 字段（可从 `.vindex` 读），并在 UI 视频列表中显示为 `2:34` 格式的时长标签。

---

## 6. 可重构模块

### REFACTOR-001 将 `clio/ui/routes/` 下的路由统一为注册表模式

**现状**: 16 个路由文件，每增一个都要在 `server.py` 中 import 并在 3 个 `do_*` 方法里加 `if` 分支。

**目标结构**:

```
clio/ui/
├── router.py          # Router 类 + 路由注册装饰器
└── routes/
    ├── _registry.py   # 所有路由的注册入口（统一 import）
    └── ...            # 各路由文件不变，但改用 @router.get("/api/xxx")
```

`server.py` 的 `do_GET` 简化为：

```python
def do_GET(self):
    result = router.dispatch("GET", url.path)
    if result:
        handler_fn, params = result
        handler_fn(self, qs, **params)
    else:
        self.send_error(404)
```

---

### REFACTOR-002 将 `analyze.py` 的 AI 调用函数提取到 `ai/` 子包

**现状**: `clio/analyze.py` 同时包含：
- AI 调用逻辑（`analyze_video`, `generate_plan`, `generate_voiceover`, `refine_analysis`）
- 数据验证（`_validate_analysis`, `_validate_plan`, `_validate_voiceover`）
- 模板读取（`_read_trip_context`）

这些逻辑与 `ai/` 子包的职责有重叠。

**建议拆分**:

```
clio/ai/
├── base.py           # 已有
├── factory.py        # 已有
├── gemini.py         # 已有
├── token_usage.py    # 已有
├── calls.py          # 新增：analyze_video / generate_plan / generate_voiceover（纯 AI 调用）
└── validators.py     # 新增：_validate_analysis 等校验函数
```

`analyze.py` 改为薄薄的 re-export 层，保持向后兼容。

---

### REFACTOR-003 `vmeta.py` 中 `VideoMeta` 和 `VideoIndex` 建议拆分到独立文件

**现状**: `vmeta.py` 包含两个概念上相对独立的类：
- `VideoMeta`：单个压缩文件的元数据（`.vmeta`）
- `VideoIndex`：一个原始文件对应的所有分段索引（`.vindex`）

加上各自的 dataclass helper、`_quick_hash`、`_meta_to_dict`，共 240 行。

**建议**（可选，低优先级）:

```
clio/
├── vmeta.py       # 保留 VideoMeta + SplitInfo（单文件元数据）
└── vindex.py      # 新增 VideoIndex + SegmentEntry（多段索引）
```

---

### REFACTOR-004 `config/` 目录中 `parsers.py` + `validators.py` + `loader.py` 的职责边界模糊

**现状**: 三个文件分别做"解析 YAML 字段"、"校验 dataclass 值"、"加载并合并配置"，但部分校验逻辑（如 `WhisperConfig.sanitize()`）在 model 层，部分在 validators 层，不一致。

**建议**: 统一校验入口——所有 dataclass 实现 `def validate(self) -> None`，`loader.py` 加载完成后统一调用 `config.validate()`（递归调用各子 config 的 `validate()`）。

---

## 7. 总结优先级表

| 优先级 | ID | 类型 | 描述 | 估计工作量 |
|--------|-----|------|------|-----------|
| P0 🚨 | BUG-001 | Bug | rerun analyze/voiceover 缺少 cancel_event | 5 分钟 |
| P0 🚨 | BUG-004 | Bug | CI 测试因 SOCKS5 依赖失败 | 5 分钟 |
| P0 🚨 | FD-001 | 功能缺陷 | 剪映导出写死 1920×1080，竖屏视频无法正常导出 | 1–2 小时 |
| P0 🚨 | FD-004 | 功能缺陷 | 剪映导出没有 UI 入口（零剪辑最后一步） | 2–4 小时 |
| P1 ⚠️ | BUG-002 | Bug | generate_voiceover 不支持 cancel_event | 30 分钟 |
| P1 ⚠️ | BUG-005 | Bug | jianying.py 大量 debug print 残留 | 15 分钟 |
| P1 ⚠️ | FD-002 | 功能缺陷 | transcripts_dir 缺少 AppConfig property | 5 分钟 |
| P1 ⚠️ | FD-005 | 功能缺陷 | reindex 调用 os.system clear 清屏 | 10 分钟 |
| P1 ⚠️ | FD-006 | 功能缺陷 | whisper 未安装时 transcribe 报错不友好 | 30 分钟 |
| P1 ⚠️ | NEW-001 | 新功能 | 自动复制剪映草稿到剪映目录（零剪辑最后一公里） | 2 小时 |
| P2 🔶 | BUG-003 | Bug | RateLimiter.__enter__ 日志竞态 | 30 分钟 |
| P2 🔶 | FD-003 | 功能缺陷 | voiceover/plan AI 调用是串行，应支持并发 | 3–4 小时 |
| P2 🔶 | OPT-002 | 优化 | ProgressTracker.logs 无上限 | 15 分钟 |
| P2 🔶 | OPT-006 | 优化 | editor.js 1228 行需要拆分（ROADMAP Phase 5） | 3–5 小时 |
| P2 🔶 | NEW-002 | 新功能 | vmeta verify CLI 命令 | 2 小时 |
| P2 🔶 | NEW-005 | 新功能 | SSE 替换轮询 | 3 小时 |
| P3 🔵 | ARCH-001 | 架构 | 路由注册表替换 if 链 | 4–6 小时 |
| P3 🔵 | ARCH-002 | 架构 | ExportConfig dataclass | 1 小时 |
| P3 🔵 | ARCH-004 | 架构 | ProcessingState 写入防抖 | 1 小时 |
| P3 🔵 | NEW-003 | 新功能 | AI 分析质量评分 + 自动重试 | 2–3 小时 |
| P3 🔵 | REFACTOR-001 | 重构 | 路由注册表模式 | 4–6 小时 |
| P3 🔵 | REFACTOR-002 | 重构 | analyze.py AI 调用提取到 ai/ 子包 | 3–4 小时 |

---

## 附：最近两天变更的质量评估

最近 40 次提交覆盖了几个关键方向，整体质量高：

**做得好的**:
- `cancel_event` 传播覆盖（analyze、compress、transcribe、label）几乎完整，仅 BUG-001/002 漏网
- `HandlerProtocol` 引入解决了 mypy 对 Handler 类的类型错误，思路正确
- `.vindex` / `.vmeta` sidecar 系统设计完整，`reindex` 命令提供了迁移路径
- `schema.py` 集中版本管理好习惯
- 测试覆盖率高（901 个测试，单文件失败属 CI 环境问题）

**需要补充的**:
- BUG-001（rerun cancel_event 漏传）是这批改动的直接遗漏，应在当前 sprint 内修复
- jianying.py 的 debug print 是开发阶段遗留，应在发 CHANGELOG 前清理
- Phase 5（frontend module splitting）已推迟，但 editor.js 的体积已经影响代码可读性，建议下一个 sprint 优先处理

---

*生成时间: 2026-06-28 | 基于 commit dd494d6*
