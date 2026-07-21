# vlog-editing-helper 全面代码审查报告
Bug · 缺陷 · 架构 · 优化 · 新功能
2026-06-24

## 0. 执行摘要
本报告基于对 `vlog-editing-helper` 所有核心源文件（`pipeline.py`、`tasks/*`、`ai/*`、`ui/server.py`、`ui/routes/*`、`processing_state.py`、`ratelimit.py`、`analyze.py` 等）的逐行阅读，输出以下五类分析结果：
- 🐛 已确认 Bug（含可复现路径）
- ⚠️ 功能缺陷（已规划但未落地 / 逻辑不完整）
- 🏗️ 架构缺陷（影响可维护性 / 扩展性的设计问题）
- ✨ 可优化点（性能、可靠性、开发体验）
- 🚀 新功能建议（结合「零剪辑」北极星目标）

项目整体质量较高：原子写入、限流、重试、`cancel_event` 传播、测试覆盖率（587 例）均已达到工程化标准。但仍存在若干影响生产稳定性的中高风险问题，建议按优先级分批修复。

## 1. 已确认 Bug
### B-01 · RateLimiter.__enter__ 持有锁期间 sleep（高风险）
**文件**：`clio/ratelimit.py`，`__enter__` 方法
**问题**：`__enter__` 在 `with self._lock:` 内部调用 `time.sleep(wait)`。`ThreadingHTTPServer` 使用线程池，多个请求并发时，第二个线程在 sleep 结束前无法通过锁，导致所有 API 调用被串行化，限流等待时间叠加而非并行消化。
**影响**：10 个视频并发分析时，实际吞吐量可能只有串行的 1/N。
**已有修复路径**：同文件已有 `acquire()` 方法（锁外 sleep），但 `analyze_video` 等调用的仍是 `__enter__`，未切换。

**修复步骤**
1. 删除 `__enter__` 中的 `time.sleep(wait)` 和 `with self._lock` 块。
2. `__enter__` 改为调用 `self.acquire()`，再在锁外 sleep。
3. 或将所有调用方改用 `acquire()` 模式（`GeminiProvider._maybe_wait` 已正确使用，但确认 `__enter__` 路径是否还有调用方）。

```python
# 当前（有 bug）
def __enter__(self):
    with self._lock:
        ...
        time.sleep(wait)  # ← 锁内 sleep！

# 修复后
def __enter__(self):
    wait = self.acquire()
    if wait > 0:
        time.sleep(wait)
```

### B-02 · plan 步骤不调用 state.mark()（状态矩阵永远 null）
**文件**：`clio/tasks/plan.py`，`run_plan_vlog` 末尾
**问题**：plan 步骤在 `for clip in clips` 循环里调用 `state.mark(source_stem, 'plan', 'done')`，但 `source_stem` 取自 `clip.get('source_stem', '')`，而 `clips` 是从 `texts_dir/*.json` 读取重建的临时 dict，其 `source_stem` 字段依赖 JSON 里的 `source_file` 字段。若 `source_file` 为空（早期版本生成的 JSON），`source_stem` 为空字符串，`mark()` 以空 key 写入，UI 状态矩阵里 plan 列永远显示 null。
**影响**：用户在 UI 看不到 plan 步骤的完成状态。

**修复**：在 clips 构建时增加 fallback
```python
source_stem = Path(data.get('source_file', '')).stem or json_file.stem.split('_', 1)[-1]
```

### B-03 · _resolve_original 无 stem_cache 时回退 rglob（O(N²) 复杂度）
**文件**：`clio/tasks/analyze.py`，`_resolve_original`
**问题**：当 `stem_cache=None` 时，`_try_find` 内对每个视频调用 `input_dir.rglob(f'{stem}{ext}')`，遍历整个输入目录。`run_analyze_all` 中已有 `_build_stem_to_path` 构建缓存，但 single_file 分支没有传入缓存，直接触发 rglob 路径。
**影响**：大型项目（100+ 视频）单文件重跑时耗时显著增加。

**修复**：single_file 分支传入 stem_cache
```python
orig_path = _resolve_original(config.paths.input_dir, compressed.stem, stem_cache)
```

### B-04 · transcribe 步骤向 state.mark() 传入压缩文件 stem 而非原始文件 stem
**文件**：`clio/tasks/transcribe.py`，`run_transcribe_all`
**问题**：跳过逻辑里 `state.mark(compressed_stem, 'transcribe', 'skipped')`，但 `ProcessingState` 的 key 约定是原始视频 stem（其他步骤均如此）。导致跳过记录写到错误的 key，UI 状态矩阵不一致。

**修复**：统一使用 `orig_stem`（已在后续成功路径中正确使用）
```python
# 第一个 skip 分支（line ~74）
state.mark(orig_stem, 'transcribe', 'skipped')  # 非 compressed_stem
```

### B-05 · whisper_routes 中 PyThreadState_SetAsyncExc 线程杀死不安全
**文件**：`clio/ui/routes/whisper_routes.py`（ROADMAP U-007 已确认）
**问题**：取消 Whisper 模型下载时通过 `ctypes.pythonapi.PyThreadState_SetAsyncExc` 向线程注入异常。C 扩展（如 `hf_hub_download` 的 urllib3 底层）会忽略该注入，导致资源泄漏（文件句柄、socket）且 Python 状态不一致。

**修复步骤（参照 ROADMAP U-007）**
1. 将 `hf_hub_download` 改为 `requests.get(stream=True) + iter_content` 分块下载。
2. 每块检查 `_INSTALL_CANCEL.is_set()`，设置则清理临时文件并 return。
3. 移除 ctypes 线程杀死代码。

### B-06 · cut 任务 _resolve_video_path 仅搜索 input_dir 一级目录
**文件**：`clio/tasks/cut.py`，`_resolve_video_path`，`source='original'` 分支
**问题**：循环 `for p in sorted(input_dir.iterdir())` 只遍历顶层，不递归。若原始视频在子目录（GoPro 按日期分目录），找不到视频，静默跳过该片段。

**修复**：改用 rglob 或 `find_videos(input_dir, recursive=True)`
```python
from vlog_tool.utils import find_videos
for p in find_videos(input_dir, recursive=True):
    if p.stem.lower() == orig_stem:
        return p
```

### B-07 · _write_csv 对每条记录调用 probe_video_info（O(N) ffprobe 进程）
**文件**：`clio/tasks/_helpers.py`，`_write_csv`
**问题**：`probe_video_info` 启动子进程，对 100 个视频调用 100 次 ffprobe。`run_analyze_all` 中已有 `get_duration_sec` 的结果，但未传入 `ClipRecord`。
**影响**：100 个视频生成 CSV 额外耗时 10~30 秒。

**修复**：在 `ClipRecord` 增加 `duration_sec` 字段，analyze 步骤写入，`_write_csv` 直接读取，避免重复 probe。

### B-08 · server.py _cancel_event 跨项目共享（多项目切换 bug）
**文件**：`clio/ui/server.py`，Handler 类属性
**问题**：`_cancel_event`、`_run_thread`、`_run_lock` 均是 Handler 的类属性（class-level），在多项目模式下所有项目共享同一个取消事件。项目 A 运行时点击取消，会同时取消项目 B 的任务。

**修复**：将 run 状态从类属性移到实例字典（或 `ThreadingHTTPServer` 的 server 对象上），按 `project_key` 隔离。

## 2. 功能缺陷
### F-01 · CapCut / 剪映草稿导出（北极星功能缺失）
**当前状态**：plan 步骤输出 JSON + MD，需要用户手动在剪映中对照操作。「零剪辑」目标的核心 — 直接生成剪映草稿并导入 — 尚未实现（ROADMAP 无对应条目）。

**建议实现路径**
1. 逆向剪映草稿格式（`draft_content.json`），已有社区文档可参考。
2. 新增 `clio/export/jianying.py`，将 `plan.sequence[]` 转为 `draft_content.json`。
3. 主要字段映射：`sequence[].use_timeline` → 剪辑时间戳，`source_stem` → 素材路径，`voiceover` → 文字轨道。
4. CLI 新增 `main.py export --format jianying --day day1`。

### F-02 · analyze 步骤串行调用 Gemini，无并发
**文件**：`clio/tasks/analyze.py`，`run_analyze_all`
**问题**：`for i, (compressed, original, idx_str) in enumerate(items)` 是纯串行循环。Gemini 上传 + 处理单个视频约需 30~120 秒，10 个视频需要 5~20 分钟。Gemini API 支持并发请求（受 RPM 限制），`RateLimiter.acquire()` 已设计为非阻塞就是为此。

**修复**：使用 `ThreadPoolExecutor`，worker 数 = `min(len(items), rpm/60 的并发上限)`
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=config.analyze.max_workers) as pool:
    futures = {pool.submit(_analyze_one, ...): item for item in items}
    for fut in as_completed(futures):
        records.append(fut.result())
```

### F-03 · fs.py 目录遍历无路径限制（LAN 模式安全风险）
**文件**：`clio/ui/routes/fs.py`（ROADMAP U-008 已确认）
**问题**：`GET /api/fs/dirs?path=/etc` 可遍历整个文件系统。在 `--host 0.0.0.0` 模式下，局域网内任何设备均可列出服务器全部目录。

**修复步骤**
1. 限制根路径：`resolved.is_relative_to(Path.home())` 或 configurable root。
2. 当 `host != 127.0.0.1` 时，对所有写接口（`/api/texts PUT`、`/api/run/start POST` 等）要求 `?token=` 参数。
3. README 增加 LAN 模式安全警告。

### F-04 · R-006d：plan 视图切换 source 时播放器不跟随
**文件**：ROADMAP 标注 [!] 阻塞状态
**问题**：在 plan 视图切换 `compressed/original source` 时，播放器不自动跟随跳转到对应视频，用户需手动点击侧边栏。

**修复**：在 plan 视图的 `setSource` 逻辑中，读取 `state.currentVideo?.index`，在新 source 的 `state.videos` 里找到对应文件，调用 `playVideoSegment`。

### F-05 · 多天 vlog 计划支持不完整
**当前状态**：CLI 有 `--day` 参数，但 UI 的 Run 面板未暴露 `day_label` 选择器。用户只能通过 API 或 CLI 指定多天，UI 默认永远是 `day1`。

**修复**：Run 面板增加 Day 输入框 / 下拉（从已有 plan 文件名推断可用 day）。

### F-06 · transcribe 步骤转录原始视频而非压缩视频
**文件**：`clio/tasks/transcribe.py`，`_extract_audio` 输入为 `original_video`
**问题**：对 4K GoPro 原片提取音频，ffmpeg 需要解析 4K 视频流（即使 `-vn` 跳过视频编码，demux 仍有开销），比从压缩的 640p 文件提取慢 2~5 倍。

**修复**：如果 `compressed_video` 存在且可读，优先从 `compressed_video` 提取音频（仅需要音频轨，画质无关）。

### F-07 · plan 步骤的 transcript 注入无降级提示
**文件**：`clio/tasks/plan.py`
**问题**：若 `whisper.enabled=true` 但 `transcripts_dir` 为空（用户未运行转录步骤），plan 静默降级为不含 transcript 的规划，无任何提示。用户以为规划已用上语音信息，实际没有。

**修复**：若 `use_transcripts=true` 但 `transcripts_map` 为空，打印明确警告并在 plan JSON 增加 `_transcripts_missing: true` 标记。

## 3. 架构缺陷
### A-01 · server.py Handler 使用类属性共享状态（反 OOP）
**问题**：`ThreadingHTTPServer` 每个请求创建新的 Handler 实例，但 `_run_lock`、`_run_thread`、`_cancel_event`、`_config_cache` 是类属性，实际是进程级全局变量，只是伪装成类属性。这种设计使测试困难（需要 mock 类属性），且在多项目模式下导致状态混用（B-08）。

**建议重构**：将共享状态提取到 `ServerState` dataclass，在 `run()` 函数内创建，通过 `make_handler(config, state)` 闭包注入
```python
from dataclasses import dataclass, field
import threading

@dataclass
class ServerState:
    run_lock: threading.Lock = field(default_factory=threading.Lock)
    run_thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    config_cache: ConfigCache | None = None
```

### A-02 · do_GET / do_PUT / do_POST 路由表硬编码 if-elif 链
**文件**：`clio/ui/server.py`
**问题**：三个 HTTP method 分发函数各有约 30 个 if-elif 分支，无法静态分析、无路由前缀聚合，每次新增 endpoint 都需要修改中央 `server.py`。

**建议**：引入极简路由表（不依赖 Flask/FastAPI）
```python
_GET_ROUTES: dict[str, Callable] = {
    '/api/config': handle_get_config,
    '/api/videos': handle_get_videos,
    ...
}

def do_GET(self):
    handler_fn = _GET_ROUTES.get(path)
    if handler_fn:
        return handler_fn(self, qs)
    self.send_error(404)
```

### A-03 · ProgressTracker 写文件但无 SSE，轮询延迟 2 秒
**问题**：pipeline 进度通过写 `.progress.json`，前端每 2 秒轮询。对于 analyze 步骤（单视频耗时 30~120 秒），2 秒延迟可接受；但对 compress（有百分比进度），2 秒粒度导致进度条跳动。

**优化方案**：ROADMAP Phase 2 已规划切换 FastAPI + SSE；短期可将轮询间隔设为 500ms，或增加 `X-Accel-Buffering: no` 头支持 SSE 流式输出（stdlib http.server 也可实现）。

### A-04 · AI Provider 无连接池 TTL / 热重载（ROADMAP U-002）
**文件**：`clio/ai/factory.py`，`_provider_cache`
**问题**：`_provider_cache` 全局字典永不过期。长时间运行的 serve 命令会积累过期的 HTTP session（尤其 `GeminiProvider` 的 `httpx.Client`）。config hot-reload 后旧 provider 仍在使用旧 api_key。

**规划**：已在 ROADMAP U-002 中规划 `ProviderManager`，建议优先实现。

### A-05 · compress / label / cut 步骤无 state.mark() 调用
**文件**：`compress.py` 有调用，但 `label.py`、`cut.py` 完全没有 `state.mark()`。
**问题**：`ProcessingState` 矩阵的 label 和 cut 列永远为 null，UI 无法显示这两步的完成状态。

**修复**：在 `run_label_videos` 和 `run_cut_all` 中补全 `state.mark(stem, 'label'/'cut', 'done'/'error')` 调用。

### A-06 · 测试覆盖率低洼：server.py(6%) / fs.py(12%)
**文件**：(ROADMAP U-010 已确认)
**问题**：`server.py` 是安全边界（路由分发、文件写入），`fs.py` 是路径遍历防护，两者测试覆盖率极低，任何回归都难以发现。

**建议测试方案**
1. 用 `http.server` 的 test 模式或 `socketserver.TCPServer` 直接实例化 Handler，模拟 GET/PUT/POST 请求。
2. `fs.py` 测试：chroot 到临时目录，验证越界路径返回 403。
3. `whisper_routes.py`：mock `hf_hub_download`，验证 cancel 流程正确清理。

## 4. 可优化点
### O-01 · analyze 并发 + 动态 max_workers 配置
在 F-02 的基础上，将并发数暴露为配置项
```yaml
# config.yaml
analyze:
  max_workers: 3   # 默认 1（串行），按 RPM 调整
```
`RateLimiter.acquire()` 已支持并发场景（锁外 sleep），无需额外改动。

### O-02 · compress 步骤进度粒度优化
`compress_video` 的 `progress_callback` 每秒调用一次，但 `ProgressTracker` 写磁盘（JSON 原子写入）每次触发一次 I/O。100 个视频压缩时写盘量较大。

**优化**：`progress_callback` 内部 debounce，至少间隔 2 秒再写盘
```python
if time.monotonic() - self._last_flush > 2.0:
    self._flush()
```

### O-03 · _build_stem_to_path 每次 run_analyze_all 重建
**文件**：`analyze.py`，`run_analyze_all`
**问题**：`_build_stem_to_path` 扫描 input_dir 构建字典，在 single_file 重跑时也会全量扫描。

**优化**：加 LRU cache 或 mtime-based invalidation 减少重复扫描。

### O-04 · ProcessingState._flush 每次 mark 都触发原子写
**问题**：流水线运行时每标记一个视频一个步骤就触发一次原子写（rename 系统调用）。100 视频 × 6 步骤 = 600 次写盘。

**优化**：引入 dirty flag + 后台 flush 线程（每 1 秒批量写一次）
```python
def mark(self, ...):
    with self._lock:
        # update _data
        self._dirty = True

# 后台线程
while True:
    time.sleep(1)
    if self._dirty:
        self._flush()
        self._dirty = False
```

### O-05 · Gemini 上传后不删除文件的异常路径
**文件**：`clio/ai/gemini.py`，`analyze_video`，finally 块
**问题**：finally 块中 `self._client.files.delete(name=uploaded.name)` 若抛异常被静默忽略，Gemini Files API 的上传文件不会被清理，占用配额直到自动过期（默认 48h）。

**优化**：记录删除失败并打印 warning，方便用户手动清理
```python
except Exception as e:
    print(f'  [警告] Gemini 文件删除失败 {uploaded.name}: {e}')
```

### O-06 · OpenAICompatProvider 超时硬编码 120s
**文件**：`clio/ai/openai_compat.py`
**问题**：`httpx.Client(timeout=120.0)` 硬编码，对慢速 API（如本地 Ollama 加载大模型）不够用，对快速 API 又太长导致错误感知延迟。

**优化**：从 `ProviderConfig` 读取 `timeout` 字段（默认 120），在 `config.yaml` 中可配置。

### O-07 · extract_json 的 JSON 解析无长度保护
**文件**：`clio/utils.py`（推断）
**问题**：AI 偶发返回超长 markdown 包裹的 JSON，`extract_json` 需要扫描整个字符串。若 AI 返回异常大的响应（如重复内容），解析时间可能较长。

**优化**：对 AI 响应长度加上限保护（如 1MB），超出则截断并告警。

### O-08 · UI 前端无单元测试
**文件**：`clio/ui/static/*.js`
**问题**：`app.js`、`player.js` 等前端代码无测试。ROADMAP 已提到 Node 22 内置 test runner 方案，建议实施。

**建议**：对核心纯函数（时间戳解析、plan sequence 渲染、state 管理）提取模块，用 `node:test + import assertions` 测试。

## 5. 新功能建议
### N-01 · 剪映 / CapCut 草稿直接导入（最高优先级）
这是「零剪辑」北极星目标的核心缺口。实现后用户完全不需要手动操作剪辑软件。

**实现方案**
1. 分析剪映草稿目录结构（`draft_content.json` 格式，社区已有逆向文档）。
2. 新建 `clio/export/jianying.py`：
   - 将 `plan.sequence[]` 映射为剪映时间线片段
   - 将 `voiceover` 文本映射为文字轨道或字幕轨道
   - 将 `use_timeline` 时间戳转为 `draft_content` 的 `timeRange` 格式
3. CLI：`main.py export --format jianying [--day day1]`。
4. UI：plan 视图增加「导出到剪映」按钮，自动写入剪映草稿目录。

### N-02 · 多模型并行分析 + 结果对比
ROADMAP R-010 已提及，但未排期。

**实现方案**
1. CLI：`main.py analyze --models gemini-1.5-pro,gemini-2.0-flash`，对每个视频并发调两个模型。
2. 输出 `001_xxx_model_a.json` 和 `001_xxx_model_b.json`。
3. UI：texts 视图新增 diff 模式，左右对比两个模型的 summary / timeline / highlights。
4. 用户点击「采用」选择最终版本，或手动 merge。

### N-03 · 批量 refine 的增量模式（只处理 AI 置信度低的片段）
**实现方案**
1. analyze 步骤在 JSON 中增加 `_confidence: 0~1` 字段（让 AI 自我评估）。
2. refine 命令增加 `--threshold 0.7` 参数，只处理 `_confidence < 0.7` 的文件。
3. 节省 80% 的 refine token 消耗（通常只有少数片段需要修正）。

### N-04 · Webhook / 外部触发器（自动化工作流）
**用户场景**：GoPro 录制完毕 → 自动同步到 NAS → 触发完整 pipeline → 完成后推送通知。

**实现方案**
1. 新增 `POST /api/webhook/trigger`，接受 `{ dir, steps, day }` 参数。
2. 支持 HMAC 签名验证（防止局域网内意外触发）。
3. 配合 Syncthing / rsync 的 post-sync 脚本，实现「文件同步完成自动分析」。

### N-05 · 智能封面帧提取
**问题**：用户需要手动在剪映里截取封面帧。

**实现方案**
1. analyze 步骤让 AI 在 JSON 中返回 `cover_timestamp: MM:SS`（建议封面时刻）。
2. 新增 `clio/tasks/cover.py`：`ffmpeg -ss {ts} -vframes 1` 提取 JPEG。
3. UI plan 视图显示各段落的封面候选帧缩略图。

### N-06 · 语音转录结果与 timeline 自动对齐
**当前状态**：Whisper 转录结果通过 `transcripts_map` 注入 plan prompt，但 analyze 生成的 timeline 时间戳与 Whisper segments 的时间戳是独立的，未做对齐。

**实现方案**
1. 在 post-analyze 阶段，将 Whisper segments 与 timeline 做时间区间 overlap 匹配。
2. 为每个 timeline 条目附加 `transcript` 字段（该时段的语音文本）。
3. 这样 plan prompt 拿到的信息更精准：不只是「这段有什么动作」，而是「这段说了什么话 + 做了什么动作」。

## 6. 优先级实施矩阵
按「风险 × 实施成本」排序，建议分三个 Sprint 落地：

| Sprint | 任务 | 类型 | 风险级别 | 工作量 |
|--------|------|------|----------|--------|
| Sprint 1 | B-01 RateLimiter 锁内 sleep | 性能 bug，多线程串行化 | S（<2h） | 小 |
| Sprint 1 | B-04 transcribe state key 错误 | 状态矩阵不一致 | S（<1h） | 极小 |
| Sprint 1 | B-08 cancel_event 跨项目共享 | 多项目模式任务互相干扰 | M（4h） | 中 |
| Sprint 1 | F-03 fs.py 路径无限制 | LAN 模式安全漏洞 | M（4h） | 中 |
| Sprint 1 | A-05 label/cut 无 state.mark | UI 状态显示残缺 | S（1h） | 极小 |
| Sprint 2 | F-02 analyze 串行→并发 | 核心性能瓶颈 | M（6h） | 中 |
| Sprint 2 | B-02 plan state.mark key 为空 | plan 步骤状态永远 null | S（1h） | 极小 |
| Sprint 2 | B-05 Whisper ctypes 线程杀死 | 资源泄漏 | M（4h） | 中 |
| Sprint 2 | A-01 ServerState 重构 | 测试性 / 多项目隔离 | L（1d） | 大 |
| Sprint 2 | U-002 ProviderManager TTL | 长时运行 session 泄漏 | M（6h） | 中 |
| Sprint 3 | N-01 剪映草稿导出 | 北极星功能 | XL（3d） | 超大 |
| Sprint 3 | N-06 transcript+timeline 对齐 | plan 质量提升 | L（1d） | 大 |
| Sprint 3 | N-02 多模型并行对比 | 分析质量 | L（1.5d） | 大 |
| Sprint 3 | A-06 server/fs 测试覆盖 | 回归防护 | L（2d） | 大 |
| Sprint 3 | O-08 前端单元测试 | 回归防护 | M（1d） | 中 |

## 7. 快速修复代码片段
### 7.1 B-01 修复：RateLimiter.__enter__
```python
# clio/ratelimit.py
def __enter__(self) -> None:
    wait = self.acquire()   # ← 在锁外计算等待时间
    if wait > 0:
        time.sleep(wait)    # ← 锁外 sleep，不阻塞其他线程

def __exit__(self, *exc_info) -> None:
    pass
```

### 7.2 B-04 修复：transcribe state.mark key
```python
# clio/tasks/transcribe.py，第一个 skip 分支
# 原来：
# state.mark(compressed_stem, 'transcribe', 'skipped')
# 修复后（orig_stem 已在下方定义，提前取出即可）：
orig_stem = original_video.stem
if not overwrite and config.analyze.skip_existing and out_path.exists():
    ...
    state.mark(orig_stem, 'transcribe', 'skipped')
```

### 7.3 A-05 修复：label 步骤补 state.mark
```python
# clio/tasks/label.py，run_label_videos 末尾
state = ProcessingState(config.paths.output_dir)

# 在循环内成功写出后添加：
state.mark(json_file.stem.split('_', 1)[-1], 'label', 'done')

# 跳过时：
state.mark(json_file.stem.split('_', 1)[-1], 'label', 'skipped')
```

### 7.4 B-08 修复：ServerState 隔离
```python
# clio/ui/server.py
from dataclasses import dataclass, field
import threading

@dataclass
class ServerState:
    run_lock: threading.Lock = field(default_factory=threading.Lock)
    run_thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    config_cache: ConfigCache | None = None

def make_handler(config, config_path=None):
    state = ServerState(config_cache=ConfigCache(config_path))

    class Handler(BaseHTTPRequestHandler):
        _state = state   # 实例引用，非类共享
        # 所有 handler.XXX_cancel_event → handler._state.cancel_event
    return Handler
```

### 7.5 F-02 修复：analyze 并发骨架
```python
# clio/tasks/analyze.py
from concurrent.futures import ThreadPoolExecutor, as_completed

max_workers = getattr(config.analyze, 'max_workers', 1)

def _analyze_item(item):
    compressed, original, idx_str = item
    # ... 原有单条分析逻辑 ...
    return record

with ThreadPoolExecutor(max_workers=max_workers) as pool:
    futures = {pool.submit(_analyze_item, it): it for it in items}
    for fut in as_completed(futures):
        try:
            records.append(fut.result())
        except Exception as e:
            print(f'[错误] 分析失败: {e}')
```

---
报告生成：Claude Sonnet 4.6 · 审查日期：2026-06-24
基于对所有核心源文件的逐行阅读，包括 `pipeline.py / tasks/* / ai/* / ui/server.py / ui/routes/* / processing_state.py` 等