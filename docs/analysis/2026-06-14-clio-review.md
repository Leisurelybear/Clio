# vlog-editing-helper — 项目深度 Code Review 报告

> 2026 年 6 月 · 全面审查版
>
> 覆盖范围：Python 后端 · 路由层 · 前端 ES 模块 · 任务层 · AI 调用 · 安全与并发

---

## 0. 执行摘要

本次 review 基于最新代码快照（344 个测试全部通过），覆盖所有 Python 模块和前端 JS。整体架构已较上次审查大幅改善——pipeline 成功拆分为 `tasks/` 层，`server.py` 从 1261 行瘦身至 459 行，`app.js` 拆分为 `src/` 模块。以下是关键发现汇总。

| 维度 | 状态 | 说明 |
| --- | --- | --- |
| 测试覆盖 | ✅ 良好 | 344 用例全绿，覆盖核心纯函数 |
| 架构结构 | ✅ 显著改善 | 路由/服务/任务已分层，最大文件 <700 行 |
| Bug（P0） | 🔴 2 个 | 全局 config 保存后缓存不失效；analyze 仅 glob `*.mp4` |
| Bug（P1） | 🟡 4 个 | `segment_matches` 字段缺失；`trip_context` 路径硬编码等 |
| Bug（P2/P3） | 🟢 7 个 | 轻微逻辑隐患，影响较小 |
| 优化机会 | 🔵 8 项 | 性能、UX、代码质量方向 |
| 新 Feature | 💡 5 个 | Whisper ASR / 草稿导出 / Tauri / 云端等方向 |

---

## 1. Bug 清单（按优先级）

### P0 — 立即修复（影响核心功能正确性）

#### P0-001：全局 `config.yaml` 保存后 `_config_cache` 未失效

**文件**：`clio/ui/routes/config_routes.py`，`handle_put_config_raw()`

**问题**：当写入的是全局 `config.yaml`（非 `project.yaml`）时，代码写盘后未对 `_config_cache` 做任何清理。后续所有的流水线调用（`/api/run/start` 等）仍然拿到旧配置，新 API key、新 provider 设置全部无效，直到服务重启。

此 bug 在 `docs/superpowers/specs/2026-06-13-config-hot-reload-audit-design.md` 中已有记录但尚未修复。

**修复方案**：

- 在 `handle_put_config_raw` 写盘成功后调用 `handler.__class__._config_cache.clear()`
- 同步修改 UI 的状态消息：仅 global `config.yaml` 写入时才显示"需重启服务生效"，`project.yaml` 写入时显示"已立即生效"（`editor.js` line 276 目前对两种情况都显示重启提示）

```python
# config_routes.py — handle_put_config_raw 末尾，全局 config 分支
_save_atomic(config_path, yml.encode("utf-8"))
with handler.__class__._config_cache_lock:
    handler.__class__._config_cache.clear()  # ← 补这两行
```

---

#### P0-002：`run_analyze_all` 扫描 glob 仅覆盖 `*.mp4`，丢失 `.mov`/`.m4v` 等格式

**文件**：`clio/tasks/analyze.py`，`run_analyze_all()`，line 73

**问题**：压缩任务的输出强制为 `.mp4`（`compress.py` 中固定后缀），但 `glob("*.mp4")` 只扫描 `.mp4` 文件，如果未来支持其他压缩格式输出则会静默丢失。`single_file` 分支（line 64）的 glob 同样仅匹配 `*.mp4`。更重要的是，该问题与 `VIDEO_EXTS` 常量已提取但未被 analyze 使用的割裂形成了隐患。

**修复方案**：

- 将 `glob("*.mp4")` 替换为对 `VIDEO_EXTS` 集合中每个扩展名的 glob，或使用 `iterdir()` 过滤
- `single_file` 分支的 `glob(f"*_{single_file.stem}*.mp4")` 同步修改

```python
# 建议替换为：
from vlog_tool._constants import VIDEO_EXTS

def _glob_compressed(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir() if p.suffix.lower() in VIDEO_EXTS)
```

---

### P1 — 近期修复（影响功能完整性）

#### P1-001：`sidebar.js` 使用 `segment_matches` 字段，但后端从未返回该字段

**文件**：`clio/ui/static/src/sidebar.js` line 119；`clio/ui/routes/videos.py`

**问题**：`sidebar.js` `renderVideoItem()` 中有如下逻辑：`if (v.segment_matches && v.segment_matches.length > 1)`。但翻查 `handle_get_videos` 的完整返回 JSON，original 视图的每个视频条目只有 `match` 字段（单个对象），从未有 `segment_matches` 字段（数组）。该分支永远不会执行，多段视频在 original 视图下显示的 match badge 是错误状态（"无对应"或单个匹配），而非"→ 压：N 段"。

**修复方案**：在 `handle_get_videos` 的 original 分支中，当一个原视频对应多个 compressed 分段时，返回 `segment_matches` 数组而非单个 `match` 对象。

---

#### P1-002：`analyze.py` 中 `trip_context.md` 路径硬编码相对于包安装位置，而非项目目录

**文件**：`clio/analyze.py`，`_wrap_with_context()`，line 33

**问题**：`trip_ctx = Path(__file__).parent.parent / "templates" / "trip_context.md"` 定位到的是 Python 包本身所在目录的 `templates/`，而非用户运行 `main.py` 的工作目录。当项目被 `pip install -e .` 安装或从不同工作目录运行时，定位可能不符合预期；更关键的是，多项目场景下每个项目应有自己的 `trip_context`，但此处总是读同一份全局文件。

**修复方案**：

- 将 `trip_context` 路径优先级调整为：① `project_dir/templates/trip_context.md` → ② config 所在目录/`templates/trip_context.md` → ③ 当前工作目录/`templates/trip_context.md`
- 将 `trip_context` 路径作为参数传入 `_wrap_with_context`，而非在函数内硬编码

---

#### P1-003：多处 `hasattr(handler.server, ...)` 防御代码表明属性绑定不可靠

**文件**：`clio/ui/routes/config_routes.py`（3 处）、`routes/projects.py`（5 处）

**问题**：`config_path` 和 `input_dir` 既可能在 `handler.server` 上，也可能直接在 `handler` 上，导致路由代码中出现 `handler.server.config_path if hasattr(handler.server, "config_path") else getattr(handler, "config_path", None)` 这类三元嵌套，散布 8 次以上。当某处漏了 `hasattr` 守护时可能 `AttributeError`。

**修复方案**：在 `make_handler` 末尾统一将关键属性绑定到 server 对象（当前仅绑定在 Handler 类上），并在路由模块中统一访问 `handler.server.config_path` 而不做 `hasattr` 检查。

---

#### P1-004：`_config_cache` 无 TTL 也无 LRU，大量项目切换后内存泄漏

**文件**：`clio/ui/server.py`，`_config_cache`

**问题**：`_config_cache` 是纯 `dict`，只有在 `/api/projects` 触发显式清除时才删除过时条目，且没有上限。如果用户长期运行服务并频繁切换项目，cache 会无限增长。`config_hot_reload_audit` 文档也记录了这个问题。

**修复方案**：引入简单 LRU（使用 `functools.lru_cache` 或 `collections.OrderedDict`）或设置 `max_size=20` 的简单门槛，超过则清空最旧条目。

---

### P2 — 中期修复（稳定性与健壮性）

| ID | 位置 | 问题描述 | 修复思路 |
| --- | --- | --- | --- |
| P2-001 | `tasks/analyze.py`, line 43 | 函数内部 lazy `import re`（在热路径中） | 移到文件顶部 `import re` |
| P2-002 | `split.py`, `split_video()` | `ffmpeg -c copy` 按时间切割在非关键帧处会导致片段开头有黑帧，AI 可能误判 | 文档说明此行为；或提供 `--reencode-split` 选项 |
| P2-003 | `progress.py`, `_flush()` | tmp 文件名用 `.progress.json.tmp`，多进程环境下可能冲突 | 改用 `os.urandom(4).hex()` 后缀（参考 `file_service.py` 的做法） |
| P2-004 | `pipeline.py`, `run_pipeline_steps()` | `steps` 参数包含未知 step 名时，`_STEP_FUNCS.get(step)` 会返回 `None`，`fn(...)` 会崩溃 | 在循环前做 `unknown_steps` 验证并提前 `raise ValueError` |
| P2-005 | `server.py`, `_send_video_range()` | Range 请求中 `end_s` 为空（`bytes=1024-`）时 `end` 被赋值 `size-1`，但计算后 `length` 可能为 0（当 `start = size-1` 时） | 对 `length <= 0` 做保护 |

---

### P3 — 长期改进（不紧急但值得修复）

| ID | 位置 | 问题描述 |
| --- | --- | --- |
| P3-001 | `tasks/compress.py` | `skip_existing` 检查的是 `use_out.exists()`，若压缩失败留下损坏的 `.mp4` 则永久跳过（不重试） |
| P3-002 | `ui/routes/videos.py` | `_parse_segment_info` 只识别 `001_GL010683_seg01` 格式，若用户自定义命名则不识别 |
| P3-003 | `analyze.py`, `_wrap_with_context()` | `trip_context.md` 每次调用都读磁盘，并发 AI 调用时会多次 I/O；可在函数外缓存 |

---

## 2. 可优化/提升的点

### 2.1 后端架构层面

#### OPT-001：路由模块对 handler 的依赖过深，难以独立测试

当前 `routes/` 下的所有函数接受 `BaseHTTPRequestHandler` 实例，通过 `handler._send_json()`、`handler._resolve_project_input()` 等方法完成工作。这导致测试必须 mock 整个 handler 对象（见 `test_routes_*.py` 中的 `MagicMock` 方式）。

**建议**：在 Phase 2 迁移 FastAPI 前，可先将纯业务逻辑从路由中提取到 `services/`，路由只做参数解析和响应组装，services 完全无 handler 依赖，可以干净地单元测试。

#### OPT-002：`ProgressTracker` 每次 `update`/`log` 都 flush 到磁盘，高频调用时 I/O 浪费

`progress.py` 的每个 `update()` 和 `log()` 都立即写 `.progress.json`。在 analyze 阶段，每条视频上传时 `_on_progress` 触发频率极高（等待 Gemini 处理期间每 `poll_interval` 触发一次）。

**建议**：加一个 `_dirty` 标记 + 基于时间的防抖（例如距上次 flush > 0.5s 才真正写盘），或使用 `threading.Timer` 延迟合并写。

#### OPT-003：`_detect_steps` 每次调用都遍历目录，但 `/api/projects` 列表每次刷新都调用

`project_service.py` 的 `_detect_steps()` 对每个项目做多次 `os.stat` + `iterdir` 调用。`/api/projects` 会为所有已知项目调用一次，如果注册了 20 个项目，每次打开侧栏下拉都触发 20 次目录扫描。

**建议**：在 `project.json` 中缓存 steps，仅在 pipeline 运行完成后更新，`/api/projects` 直接读缓存；或对 `_detect_steps` 结果加 mtime 缓存（以 `proj_output_dir` 的 mtime 为 key）。

---

### 2.2 前端层面

#### OPT-004：`sidebar.js` 658 行，承担了太多职责

经过模块拆分，`sidebar.js` 仍是最大的 JS 文件（658 行），混合了数据加载（`loadProjects`/`loadVideos`）、渲染（`renderVideoList`/`renderVideoItem`）、选择逻辑（`selectVideo`/`selectPlan`）、目录浏览（`openBrowseDir`/`loadBrowseDir`）、Rerun 进度轮询（`showRerunProgress`/`pollRerunStatus`）等。

**建议**：将 rerun 进度逻辑（`showRerunProgress`、`hideRerunProgress`、`pollRerunStatus`、`refreshAfterRerun`）提取到 `rerun.js`；将目录浏览（`openBrowseDir`、`loadBrowseDir`）提取到 `browser.js`；`sidebar.js` 专注视频列表渲染和导航选择，目标 <300 行。

#### OPT-005：`window._browseResolve` 通过全局变量跨模块通信，是反模式

`sidebar.js` 将 `window._browseResolve` 挂在 `window` 上，`main.js` 读它。这是 ES 模块时代的全局变量反模式，容易被意外覆盖，也使调用链难以追踪。

**建议**：用 `CustomEvent` 或模块级的 resolve 回调变量（在 `browser.js` 模块内维护），通过 `openBrowseDir(callback)` 的形式传入，避免污染 `window`。

#### OPT-006：进度仍是 2s 轮询，rerun 与全局 pipeline 共用同一个 `/api/run/status`

当前 rerun 的进度面板和全局运行面板都读 `/api/run/status`，而后端只有一个 `.progress.json` 文件。如果用户在全局 pipeline 运行时触发 rerun，进度数据会互相覆盖，UI 展示混乱。

**建议**：为 rerun 单独维护一个 `.rerun_progress.json`（`ProgressTracker` 中已有 `rerun=True` 标记，可利用此标记写到不同文件）；或在 `/api/run/status` 的响应中区分 `type: "pipeline" | "rerun"`，前端根据类型路由到不同面板。

---

### 2.3 AI 调用层面

#### OPT-007：`extract_json` 对截断 JSON 的容错有限

`utils.py` `extract_json()` 先整体 `json.loads`，失败后用正则 `{[\s\S]*}` 匹配第一个 `{...}`。对于 AI 在 JSON 中包裹了 markdown 或在 JSON 后追加了文字的情况，正则可以应对；但如果 AI 返回的 JSON 本身有截断（超出 token 上限），则两者都会失败并抛 `ValueError`，导致整条视频分析结果丢失。

**建议**：在 retry 逻辑外层加 partial JSON 检测——当 `ValueError` 发生时，尝试提取已有的字段（如 `title`、`summary`）写入一个 `partial=True` 的结果，标记为需要 refine，而非完全跳过这条视频。

#### OPT-008：`RateLimiter` 的 `_logged` 标记逻辑是多余的

`ratelimit.py` `RateLimiter` 的 `_logged` 字段意图是"只打印一次等待"，但在 `__enter__` 中一旦 sleep 结束后立即 `self._logged = False`。实际上 `_logged` 从未真正抑制重复日志（每次进入 `__enter__` 时 `_logged` 都为 `False`），逻辑是多余的。

**建议**：移除 `_logged` 标记，改为限流时每次都打印（用户反馈更透明），或改用 `total_wait` 累积阈值才打印。

---

## 3. 新 Feature 方向

### F-001：Whisper 本地语音转写集成（高优，与 zero-edit 愿景直接相关）

**背景**：当前 AI 分析依赖 Gemini 视觉理解，口播内容来自 AI 创作。但如果视频中有实际对话或旁白（如旅行中的解说、Vlog 本人讲话），Whisper ASR 能提供准确的文字稿，大幅提升 AI 生成口播的贴合度。

**技术路径**：

- 新增 `whisper_transcribe` task（`whisper.cpp` 本地 / OpenAI Whisper API 二选一，由 config 控制）
- 提取原始视频音轨后送入 Whisper，输出时间戳字幕 `.srt` 存入 `output/transcripts/`
- 在 `ANALYZE_PROMPT` 中注入转写文本，让 AI 理解"人说了什么"而非只看画面
- UI 在 texts tab 增加 transcript 展示区（可编辑，用于修正 ASR 错误）

**影响**：这是 ROADMAP 中已有记录但未实现的项，实现后 AI 生成的口播文案质量将质变。

---

### F-002：剪映/CapCut 草稿 JSON 直接导出（零剪辑愿景的核心里程碑）

**背景**：当前工作流的终点是生成 `plan.json` + 口播 `.md`，用户还需要在剪映里手动按 plan 排列片段、粘贴文案。实现草稿导出后，用户只需用剪映"打开项目"即可看到预排好的时间线。

**技术路径**：

- 逆向解析剪映项目文件格式（已有社区文档），实现 `plan.json` → `draft.json` 的映射
- 新增 `export --format jianying` CLI 命令
- UI 中 plan 面板新增"导出草稿"按钮，生成 `.draft` 文件并提示复制到剪映项目目录

---

### F-003：批注/亮点标记系统

**背景**：用户在浏览视频时会发现特别精彩的片段，希望快速标记（不同于 AI 分析的 `highlights`，这是人工主观判断）。目前没有机制支持这种"人工标注"。

**技术路径**：

- 在播放器面板增加"标记亮点"按钮（快捷键 `M`），将当前时间戳写入视频对应的 texts JSON 的 `manual_highlights` 字段
- plan 面板中手动亮点高亮显示，AI 规划时可优先考虑有人工标注的段落
- UI 时间轴上可视化显示亮点标记点

---

### F-004：多设备/多日素材自动按日期分组

**背景**：当前项目是单文件夹平铺，一次旅行多天的素材需要用户手动分成多个项目目录。GoPro 文件名中包含拍摄时间（`GL010683` 中 `01` 是日期偏移，或 exif 数据中有精确时间），可以自动识别。

**技术路径**：

- 新增 `ingest` 命令，扫描输入目录，用 ffprobe 读取视频 exif/`creation_time`，按日期分组
- 自动创建 `day1/`、`day2/`、... 子目录并软链接（或复制）原视频
- 每个子目录作为一个独立项目，共享全局 config 的 AI 配置但有各自的 `output/`

---

### F-005：Tauri 桌面端（按上次规划文档推进）

**背景**：上次规划文档已详细设计此方向。FastAPI 迁移（Phase 2）完成后可进入 Phase 3。

**新的考虑点（基于本次代码审查）**：

- `project.json` + `project.yaml` 的双配置文件体系在桌面端需要统一，建议桌面端用 SQLite 替代 JSON 文件管理项目元数据，避免文件冲突
- 多项目切换（R-007 已实现）是桌面端的核心 UX，建议在 Tauri 中用原生侧边栏（macOS 风格）替代当前的下拉框
- API Key 存储迁移到系统 Keychain（macOS Security framework / Windows Credential Manager）

---

## 4. 新引入的亮点（值得肯定的改进）

以下是本次迭代中新引入的、质量较高的设计，值得在后续保持风格一致。

| 亮点 | 位置 | 说明 |
| --- | --- | --- |
| 视频分割（`split.py`） | `clio/split.py` | 支持超长视频自动按时长切段，再分别上传 Gemini，优雅解决 Gemini 视频长度限制 |
| 分组显示（segment grouping） | `routes/videos.py` + `sidebar.js` | 分段压缩的视频在 UI 中按原始文件名分组折叠，设计到位 |
| `RateLimiter` | `clio/ratelimit.py` | 线程安全的令牌桶实现，接口简洁（context manager），API 调用限流透明 |
| config.yaml 热重载（partial） | `config_routes.py` + `server.py` | `project.yaml` 保存后立即生效（`cache.pop`），设计方向正确 |
| `_constants.py` 集中常量 | `clio/_constants.py` | 消除 B-019 重复定义，且区分了 `VIDEO_EXTENSIONS`（扫描用）和 `VIDEO_EXTS`（服务用） |
| 任务层拆分完整 | `clio/tasks/` | 6 个独立 task 文件，`pipeline.py` 仅 96 行，各阶段可独立测试 |
| 多项目注册表 | `project_service.py` | `projects.json` + `last_project` 设计干净，支持跨目录项目管理 |

---

## 5. 完整 Bug 优先级矩阵（速查表）

| ID | 优先级 | 文件 | 一句话描述 | 修复难度 |
| --- | --- | --- | --- | --- |
| P0-001 | 🔴 P0 | `config_routes.py` | 全局 config 保存后缓存不失效，新配置无效直到重启 | ⭐ 1 行 |
| P0-002 | 🔴 P0 | `tasks/analyze.py` | glob 仅 `*.mp4`，其他格式压缩输出被静默忽略 | ⭐⭐ 简单 |
| P1-001 | 🟡 P1 | `routes/videos.py` | `segment_matches` 字段前端存在但后端从未返回 | ⭐⭐⭐ 中 |
| P1-002 | 🟡 P1 | `analyze.py` | `trip_context.md` 路径硬编码为包目录，多项目场景错误 | ⭐⭐ 简单 |
| P1-003 | 🟡 P1 | `routes/config`, `projects` | `hasattr(handler.server,...)` 防御代码散布 8 处 | ⭐⭐ 简单 |
| P1-004 | 🟡 P1 | `server.py` | `_config_cache` 无 TTL/LRU，长时间运行内存泄漏 | ⭐⭐ 简单 |
| P2-001 | 🔵 P2 | `tasks/analyze.py` | lazy `import re` 在热路径中，移到顶部 | ⭐ 1 行 |
| P2-002 | 🔵 P2 | `split.py` | `-c copy` 分割有黑帧，AI 可能误判 | ⭐⭐⭐ 需权衡 |
| P2-003 | 🔵 P2 | `progress.py` | tmp 文件名固定，多进程可能冲突 | ⭐ 1 行 |
| P2-004 | 🔵 P2 | `pipeline.py` | 未知 step 名称导致 `NoneType` 调用崩溃 | ⭐⭐ 简单 |
| P2-005 | 🔵 P2 | `server.py` | Range 请求边缘 `length=0` 未保护 | ⭐⭐ 简单 |
| P3-001 | ⚪ P3 | `tasks/compress.py` | 损坏的 `.mp4` 会被 `skip_existing` 永久跳过 | ⭐⭐⭐ 需判断 |
| P3-002 | ⚪ P3 | `routes/videos.py` | `_parse_segment_info` 格式假设太严格 | ⭐⭐ 简单 |
| P3-003 | ⚪ P3 | `analyze.py` | `trip_context.md` 每次 AI 调用都读磁盘 | ⭐ 加缓存 |

---

*— END —*
