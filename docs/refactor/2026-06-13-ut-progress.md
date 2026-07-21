# UT 进度跟踪

> 按 `docs/refactor/2026-06-13-ut-improvement.md` 优先级系统补充单元测试。
> 每完成一个模块记录：新增测试数、mock 方式、发现的潜在问题。

---

## 已完成模块

### 1. `vlog_tool/ai/*` — AI 模块（12 测试）

**文件**: `test_ai.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestTaskName` | 1 | `TaskName` 枚举值正确性 |
| `TestGetTaskConfig` | 4 | 已知/未知 task 查找、string/enum 入参、多 provider 路由 |
| `TestBuildProvider` | 2 | 未知 provider 名、不支持的类型报错 |
| `TestGetTaskProvider` | 3 | gemini/deepseek task 正确实例化、string 入参 |
| `TestGetVideoProvider` | 1 | Gemini 支持视频分析 |
| `TestOpenAICompatHasNoAnalyzeVideo` | 1 | OpenAI 兼容 provider 的 `analyze_video` 抛 `NotImplementedError` |

**mock 方式**: 配置使用 inline `api_key`（非 `api_key_env`），避免依赖真实环境变量；provider 实例化不 mock，但 API 调用（`analyze_video`）不触发。

**潜在问题**: 无

---

### 2. `vlog_tool/ui/services/file_service.py` — 文件系统服务（60 测试）

**文件**: `test_file_service.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestIsSafeBasename` | 8 | 空/长/路径穿越/控制字符/CJK 标点 |
| `TestFindTextsDirs` | 5 | 空目录/多 texts 目录/非 texts 目录/不存在 |
| `TestSaveAtomic` | 5 | 写文件/创建父目录/备份创建/备份不覆盖/tmp 清理 |
| `TestFindOriginalForCompressed` | 8 | 精确匹配/大小写/未匹配/无下划线/不存在目录/`_segNN` 回退/无原始文件/首个下划线后缀 |
| `TestFindCompressedForOriginal` | 11 | 精确匹配/未匹配/不存在目录/多段排序/优先级/大小写/`_seg` 非误配/非数字后缀/非视频扩展/无下划线 |
| `TestCoerceConfigTypes` | 18 | bool/int/float/str/list/dict/None/边界 |
| `TestCreateProjectYaml` | 5 | 无配置/缺失配置/创建/已存在不覆盖/ai.context 默认 |

**mock 方式**: 无 — 全部使用 `tmp_path` 真实文件系统。

**潜在问题**: 排序使用 index 字符串（`m[1]`）而非 segment number。当前行为是 index lexicographic sort，若 index 和 segment number 顺序不一致可能导致 UI 中 segment 顺序与视频实际顺序不符。

---

### 3. `vlog_tool/tasks/_helpers.py` — 任务助手（20 测试）

**文件**: `test_helpers.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestNextIndex` | 8 | 不存在目录/空目录/最大索引/无下划线/非数字前缀/混合/大索引/自定义宽度 |
| `TestBuildStem` | 2 | 基本/sanitize |
| `TestEtaLine` | 2 | 首项无 ETA/有 ETA |
| `TestWriteTextFile` | 2 | 基本结构/空分析 |
| `TestRewriteTextFile` | 2 | 无 changelog/有 changelog |
| `TestRewriteScriptMd` | 2 | 基本/有 changelog |
| `TestWriteCsv` | 2 | 有记录/空记录 |

**mock 方式**: `probe_video_info` 使用 `monkeypatch.setattr` 替代（CSV 测试）。

**潜在问题**: 无

---

### 4. `vlog_tool/tasks/analyze.py` — `_resolve_original`（10 测试）

**文件**: `test_analyze.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestResolveOriginal` | 10 | mp4/mov/mkv/mts/m2ts 扩展名匹配、未匹配、`_segNN` 段匹配（mov/mp4）、段无原始文件、空目录 |

**mock 方式**: 无 — 纯文件系统操作。

**潜在问题**: 无

---

### 5. `vlog_tool/ui/services/project_service.py` — 项目管理（22 测试）

**文件**: `test_project_service.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestProjectOutputDir` | 4 | 默认/绝对路径/相对路径/损坏 JSON |
| `TestRegistryPath` | 2 | 有配置/无配置 |
| `TestAddToRegistry` | 4 | 新建/追加/去重/保留 last_project |
| `TestSaveLastProject` | 1 | 基本保存 |
| `TestDetectSteps` | 9 | 全部 false/空输出/compress/analyze/scripts/plans/label/cut |
| `TestListProjects` | 3 | 无 registry fallback/registry 读取/兄弟自动发现 |

**mock 方式**: 无 — 全部使用 `tmp_path` 真实文件系统。

**潜在问题**: 无

---

### 6. `vlog_tool/ui/routes/videos.py` — 视频路由（16 测试）

**文件**: `test_routes_videos.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestParseSegmentInfo` | 9 | 无下划线/无 seg 后缀/基本段/多数字段/误配 `_seg` 前缀/尾部文本/仅有 `_seg`/空字符串 |
| `TestHandleGetVideos` | 4 | source=compressed/source=original/无效 source/分组填充 |
| `TestHandleGetVideo` | 3 | 发送视频/禁止 basename/未找到 |

**mock 方式**: `MagicMock` 替代 `BaseHTTPRequestHandler`，配置 `_resolve_project_input`/`_get_project_output`/`_send_json`/`_send_video_range` 返回值。

**潜在问题**: 无

---

### 7. `vlog_tool/ui/routes/plan.py` — 计划路由（8 测试）

**文件**: `test_routes_plan.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestHandleGetPlans` | 2 | 无 plans 目录/列出计划 |
| `TestHandleGetPlan` | 3 | 禁止 day/未找到/存在 |
| `TestHandlePutPlan` | 2 | 禁止 day/保存计划 |
| `TestHandlePostCut` | 1 | 无效 source |

**mock 方式**: `MagicMock` 替代 handler。

**潜在问题**: 无

---

### 8. `vlog_tool/ui/routes/config_routes.py` — 配置路由（6 测试）

**文件**: `test_routes_config.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestHandleGetConfig` | 1 | 基本返回路径 |
| `TestHandleGetConfigRaw` | 2 | needs_init/返回合并配置 |
| `TestHandlePostConfigInit` | 1 | 默认项目不需 init |
| `TestHandlePutConfigRaw` | 2 | 无 config_path/写入 project.yaml |

**mock 方式**: `MagicMock` 替代 handler，配置 `server.config_path`/`server.input_dir` 属性。

**潜在问题**: 无

---

### 9. `vlog_tool/tasks/compress.py` — run_compress_all 编排（3 测试）

**文件**: `test_tasks_compress.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestRunCompressAll` | 3 | compress_single_file / skip_existing / single_file_param |

**mock 方式**: `monkeypatch.setattr` mock `compress_video` / `split_video` / `_next_index` / `resolve_binary`，避免实际 ffmpeg 调用。

**潜在问题**: 无

---

### 10. `vlog_tool/tasks/analyze.py` — run_analyze_all 编排（6 测试）

**文件**: `test_tasks_analyze.py`

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| `TestRunAnalyzeAll` | 6 | 单文件 / skip_existing / 时长门控超长跳过 / 时长门控正常 / 无原始文件跳过 / 空目录 |

**mock 方式**: `monkeypatch.setattr` mock `resolve_binary`（analyze + _helpers 双模块）/ `probe_video_info` / `get_duration_sec` / `analyze_video` / `_build_stem` / `_write_text_file`。

**潜在问题**: 无

---

## 汇总

| 模块 | 新测试 | mock 内容 | 潜在问题 |
|------|--------|-----------|----------|
| `ai/*` | 12 | inline api_key 避免 env 依赖 | 无 |
| `file_service.py` | 60 | 无（真实文件系统） | 排序用 index 而非 segment number |
| `tasks/_helpers.py` | 20 | `probe_video_info` | 无 |
| `tasks/analyze.py` | 10 | 无（纯文件系统） | 无 |
| `project_service.py` | 22 | 无（真实文件系统） | 无 |
| `routes/videos.py` | 16 | `MagicMock` handler | 无 |
| `routes/plan.py` | 8 | `MagicMock` handler | 无 |
| `routes/config_routes.py` | 6 | `MagicMock` handler | 无 |
| `tasks/compress.py` | 3 | resolve_binary, compress_video, split_video | 无 |
| `tasks/analyze.py` | 6 | resolve_binary, get_duration_sec, analyze_video | 无 |
| **总计** | **163** | | |

## 后续优先项

- `tasks/cut.py::run_cut_all` — cut 编排（需 mock ffmpeg）
- `tasks/refine.py` / `tasks/scripts.py` / `tasks/plan.py` / `tasks/label.py` — AI 编排
- `vlog_tool/pipeline.py` — 高层流水线函数（`run_analyze_all` 等已完成）
