# 项目-视频管理重构设计

> 日期: 2026-07-11
> 状态: 已实现（`feat/project-video-manager`，2026-07-15）

## 1. 动机

### 问题

1. **`project_dir` == `input_dir`**: `project.yaml` 和 `project.json` 必须和原始视频在同一个目录，无法将项目配置与视频存储分离。
2. **单 `input_dir` 限制**: 只能扫描一个目录的所有视频，不支持视频分散存储在多个位置（多个硬盘、手机、相机卡等）。
3. **无法选择视频**: 扫描 `input_dir` 会包含所有视频文件，无法排除不需要的素材。

### 目标

- 项目目录仅存储配置和元数据，视频可以来自文件系统任意位置
- 用户通过 UI 内嵌文件浏览器勾选视频
- 现有项目一键迁移到新结构
- 保持向后兼容（迁移工具）

## 2. 核心概念

| 概念 | 说明 |
|---|---|
| **项目目录** | 用户创建项目时任意选择，存放 `project.yaml`、`project.json`、`videos.json` |
| **视频列表** | 用户从任意位置勾选的视频绝对路径，保存在 `videos.json` |
| **输出目录** | 独立配置，默认 `<project_dir>/output/`，用户可改 |
| **注册表** | `projects.json` 记录所有已知项目的 `project_dir`、`output_dir`、`name` |

## 3. 数据结构

### 3.1 项目目录

```
<user-chosen-project-dir>/
├── project.yaml       # 项目配置（删除 paths.input_dir）
├── project.json       # UI 运行时状态
└── videos.json        # 选中视频路径列表（绝对路径）
```

注: `.vmeta`/`.vindex` 仍在 `output_dir/compressed/` 中（与压缩文件并列），不在项目目录。

### 3.2 videos.json 格式

顶层数组，每个元素是视频文件的**绝对路径**（OS 原生格式）：

```json
[
  "D:/GoPro/trip1/GH010001.MP4",
  "D:/GoPro/trip1/GH010002.MP4",
  "E:/phone/videos/20240711_123456.mp4"
]
```

- 路径始终为绝对路径
- Windows 使用正斜杠或双反斜杠（保持一致性）

### 3.3 project.yaml 变化

**删除字段:**
- `paths.input_dir`
- `paths.recursive`（不再需要）

**保留字段:**
- `paths.output_dir`（默认 `./output`，相对于 project_dir，可改为绝对路径）
- `ai.tasks`、`ai.context` 等
- `compress`、`analyze`、`script`、`plan`、`export`、`whisper`

### 3.4 注册表 projects.json 格式

位于 `<app_root>/projects.json`：

```json
{
  "projects": [
    {
      "project_dir": "C:/Users/me/vlog-projects/trip1",
      "output_dir": "E:/output/trip1",
      "name": "巴黎2024"
    }
  ],
  "last_project": "C:/Users/me/vlog-projects/trip1"
}
```

- `project_dir` 为项目目录的绝对路径
- `output_dir` 为绝对路径（如果 project.yaml 配置了相对路径，注册表存 resolve 后的绝对值）
- 移除现有的 `input_dir` 字段

## 4. 关键文件变化

### 4.1 配置模型 (`clio/config/models.py`)

```python
# ProjectPathsConfig 删除 input_dir、recursive
@dataclass
class ProjectPathsConfig:
    output_dir: Path = Path("./output")

# CombinedPaths 删除 input_dir、recursive 属性
```

### 4.2 配置加载器 (`clio/config/loader.py`)

- `load_project_config()`: 不再解析 `paths.input_dir` 和 `paths.recursive`
- `apply_run_paths()`: 删除 `input_dir` 参数，只保留 `output_dir`
- `_path()` 函数**保留**（仍用于 `output_dir`/`template_file`/`context_file` 解析），仅不再传入旧 `input_dir`

### 4.3 视频加载

新增 `clio/tasks/_video_loader.py`（或类似位置）：

```python
def load_selected_videos(project_dir: Path) -> list[Path]:
    """从 project_dir/videos.json 读取选中视频列表。"""
    ...

def save_selected_videos(project_dir: Path, videos: list[Path]) -> None:
    """保存选中视频列表到 project_dir/videos.json。"""
    ...
```

### 4.4 视频发现替换

所有现存 `find_videos(config.paths.input_dir)` 替换为 `load_selected_videos(project_dir)`。

注意: `transcribe.py` 等模块扫描 `compressed_dir` **不替换**（那是搜索压缩输出，不是原始视频）。

受影响模块（需替换 `find_videos(input_dir)` 调用）:
- `clio/tasks/compress.py` — 原始视频列表来自 `videos.json`
- `clio/tasks/analyze.py` — `_build_stem_to_path()` 改用 `videos.json` 路径
- `clio/tasks/transcribe.py` — `_build_original_stem_map()` 改用 `load_selected_videos()`
- `clio/tasks/cut.py` — `_resolve_video_path()` 回退扫描 `videos.json`
- `clio/tasks/reindex.py` — `_find_original_for_stem()` 回退扫描 `videos.json`
- `clio/ui/services/run_preview.py` — 视频列表来自 `videos.json`
- `clio/ui/services/file_service.py` — `_find_original_for_compressed()` 改用 `videos.json`

无需修改（扫 compressed_dir 而非 input_dir）:
- `clio/tasks/compress.py` — 扫描 `compressed_dir` 做已存在检查
- `clio/tasks/transcribe.py` — 扫描 `compressed_dir` 找压缩视频
- `clio/tasks/analyze.py` — `_list_compressed()` 扫 `compressed_dir`

### 4.5 sidecar 文件位置（关键发现）

`.vmeta` 和 `.vindex` 文件**实际上不在 project_dir**，而是在 `output_dir/compressed/` 下:

| 文件类型 | 实际位置 | 路径策略 |
|---|---|---|
| `.vmeta` | `<output_dir>/compressed/<stem>.vmeta` | `source_path`=绝对路径, `target_path`=文件名 |
| `.vindex` | `<output_dir>/compressed/<orig_stem>.vindex` | `source_path`=绝对路径 |

因为 `source_path` 存的是**绝对路径** (`source.resolve()`)，这些文件不依赖 `input_dir`，**无需迁移**。新模型下它们继续在 `compressed_dir` 正常工作。

所以项目目录不包含 `.vmeta`/`.vindex`，只包含项目配置和视频索引:**

```
<project_dir>/
├── project.yaml       # 项目配置
├── project.json       # UI 状态
└── videos.json        # 视频路径列表
```

### 4.6 加载 AppConfig

`load_config()` 继续接受 `project_dir` 参数（指向项目目录，其下应有 `project.yaml`）。新逻辑：

```python
def load_config(config_path="config.yaml", project_dir: Path | None = None) -> AppConfig:
    """project_dir = 项目目录（含 project.yaml）。"""
```

`load_project_config()` 现在从 `project_dir` 读取 `videos.json` 等文件，不再解析 `paths.input_dir`。

**关键：AppConfig 需新增 `project_dir: Path | None` 属性**，保存项目目录的绝对路径。

原因：当前运行时代码通过 `config.paths.input_dir` 间接拿到项目目录，例如：
- `clio/analyze.py:121` — `_read_trip_context(str(config.paths.input_dir))`
- `clio/prompt_overrides.py` — `_project_dir()` 靠 `template_file.parent.parent` 反推

移除 `input_dir` 后，这些代码失去项目目录来源。改为：

```python
class AppConfig:
    def __init__(self, *, global_cfg, project_cfg=None, project_dir: Path | None = None):
        self._project_dir = project_dir.resolve() if project_dir else None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir
```

调用方改为：
- `_read_trip_context(str(config.project_dir))`
- `_project_dir(config)` 直接返回 `config.project_dir`（删除启发式）

`loader.py` 的 `_load_context()` 已接收 `project_dir` 参数，无需改。

### 4.7 `files` 参数与 `videos.json` 的关系

管道已有 `files: list[str] | None` 参数（`_helpers._selected_stems()` + `_matches_selected_stem()`），用于在单次运行时过滤视频。

新模型下两层过滤:

```
videos.json (项目主列表) → files 参数 (单次运行子集) → 处理
```

- `videos.json` 是项目的**完整视频清单**
- `files` 参数（CLI `--file` 或 UI 的"选中文件"）在清单**之内**过滤
- 管道步骤: `for video in load_selected_videos(project_dir): if _matches_selected_stem(video, selected): process(video)`
- 不传 `files` = 处理 `videos.json` 中所有视频（当前行为：处理 input_dir 中所有视频）

### 4.8 UI 原始视频服务

当前原始视频预览通过 `_resolve_original_video_path(proj_input, fname)` 服务，路径相对于 `input_dir` 解析。

新模型修改:
- `GET /api/video?source=original&file=<path>` 改为从 `videos.json` 中查找完整绝对路径
- 不再需要相对 `input_dir` 解析
- 安全校验: 检查请求的 file 路径是否在项目的 `videos.json` 列表中（白名单模式），而不是基于目录前缀
- `GET /api/videos?source=original` 直接返回 `videos.json` 内容，不再扫描目录

### 4.9 cut.py 原始视频解析

`cut.py` 的 `_resolve_video_path(idx)` 当 `source="original"` 时，通过 `.vmeta.source_path` 或回退 `find_videos(input_dir)` 查找原始文件。

新模型: 回退路径改为扫描 `load_selected_videos(project_dir)`，而非 `input_dir`。

### 4.10 project.json 迁移

`project.json` 目前位于 `input_dir`（旧 project_dir）。迁移时:

1. 从旧位置读取 `project.json`
2. 写入新的 `project_dir/project.json`
3. 更新 `project_dir` 字段（新路径）
4. 保留所有 UI 状态字段（`name`, `currentDay`, `source`, `lastEntity`, `lastVideo`）
5. 删除旧位置的 `project.json`（或备份）

### 4.11 `prompt_overrides.py` 启发式修复

`prompt_overrides.py` 中的 `_project_dir()` 函数通过 `template_file.parent.parent` 反向推断 project_dir。新模型下 project_dir 显式可用，应改为直接从 `config` 获取。

### 4.12 路径解析一致性

所有相对路径解析相对于 `project_dir`（`project.yaml` 所在目录）:

| 字段 | 解析基准 | 默认值 |
|---|---|---|
| `paths.output_dir` | `project_dir` | `./output` |
| `script.template_file` | `project_dir` | `./templates/vlog_template.md` |
| `ai.context_file` | 优先 `project_dir`，回退 `config_base` | 空 |

如果 `project.yaml` 迁移到新目录，模板和上下文文件路径的相对解析需要验证。

### 4.13 视频配置路由（API 风格）

复用现有 `?input_dir=<path>` 查询参数风格（避免在 URL 路径里塞完整文件系统路径，编码易出错）。将参数名从 `input_dir` 改为 `project_dir`，语义仍是「项目目录」。

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/videos?source=original&project_dir=<path>` | GET | 获取视频列表（来自 `videos.json`） |
| `/api/projects/videos?project_dir=<path>` | POST | 添加视频（body: `{paths: [...]}`） |
| `/api/projects/videos?project_dir=<path>` | DELETE | 移除视频（body: `{paths: [...]}`） |
| `/api/fs/videos?path=<dir>` | GET | 浏览目录，返回该目录下的视频文件列表 |

注：`handler._resolve_project_input(qs)` 改名为 `_resolve_project_dir(qs)`，读取 `project_dir` 查询参数（同时保留 `?project=<name>` 按名查找）。所有路由里的 `proj_input` 变量统一改名为 `proj_dir`。

### 4.14 其他受影响的代码点（审查补充）

除 4.4 列出的 `find_videos(input_dir)` 调用外，还有以下位置使用 `input_dir`，需同步修改：

**后端:**
- `clio/analyze.py:121`（`_wrap_with_context`）— 用 `config.paths.input_dir` 查 `templates/trip_context.md`。改为用 `project_dir`（即 `project.yaml` 所在目录）。
- `clio/doctor.py:131-136, 177-178` — 诊断信息里用 `input_dir` 检查素材目录。改为读 `videos.json` 列表或提示「无 input_dir 概念，请用项目视频列表」。
- `clio/ui/routes/export.py:63`（`jianying` 导出）— 用 `cfg.paths.input_dir` 定位原始视频源。改为从 `videos.json` 解析源视频绝对路径。
- `clio/ui/routes/config_routes.py:43, 187` — GET 配置响应里含 `"input_dir": str(proj_input)`；可编辑路径集合 `"paths": {"input_dir","output_dir","recursive"}`。改为移除 `input_dir`/`recursive`，新增字段改为只保留 `output_dir`，并补充 `project_dir`。
- `clio/ui/routes/whisper_models.py:140` 等 `proj_yaml = proj_input / "project.yaml"` — `proj_input` 改名 `proj_dir` 即可（概念一致）。
- `clio/ui/services/run_preview.py:37, 98-100` — 返回 `{"mode": "directory", "path": str(input_dir), "count": ...}`。新模型无单一 input_dir，改为返回 `{"mode": "videos", "count": len(videos), "videos": [...]}`，其中 videos 取自 `load_selected_videos(project_dir)`。

**前端 (`clio/ui/static/src/*.js`):**
- `api.js:22`、`runner_main.js:301`、`runner.js:84,259,322`、`main.js:44-153`、`sidebar-data.js:18,35,37,38,314,323` — 所有 `state.currentProjectInputDir` 改名 `state.currentProjectDir`；`state.config.input_dir` 改名 `state.config.project_dir`；`p.input_dir` 改名 `p.project_dir`。
- `runner.js:84` 的 `run-input-dir` 输入框（`placeholder="留空则使用当前项目的 input_dir"`）— 删除该输入框（新模型无 input_dir 概念）。
- `main.js:74,79,97,121,136,149,153` 的 `POST /api/project/create`、`/add`、`/remove` body 里 `input_dir` 字段 — 改为 `project_dir`。
- 项目卡片渲染 `Input: ${p.input_dir}` — 改为显示 `项目目录: ${p.project_dir}`。

**配置示例文件:**
- `config.example.yaml` 注释里 `paths: input_dir, output_dir, recursive` — 删除 `input_dir`/`recursive` 说明。
- `docs/project.example.yaml` 的 `paths:` 段 — 删除 `input_dir: "./videos"` 和 `recursive`，保留 `output_dir`；新增注释说明视频通过 UI 内嵌浏览器勾选，存于 `videos.json`。

**测试 (`clio/tests/`):**
- `test_run_preview.py`、`test_tasks_cut.py`、`test_tasks_compress.py`、`test_tasks_label.py`、`test_whisper_cli.py` 等直接构造 `ProjectPathsConfig(input_dir=...)`。移除 `input_dir` 字段后这些会报错，需改用 `ProjectPathsConfig(output_dir=...)` 并通过 `videos.json` 提供测试视频路径（或新增 fixture 写 `videos.json`）。

## 5. UI 变化

### 5.1 内嵌文件浏览器

新增文件浏览器组件，具有:
- 目录树导航（盘符/根 → 子目录）
- 文件列表显示，过滤出视频文件（扩展名: .mp4, .mov, .avi, .mkv 等）
- 复选框选择/取消选择
- 已选状态标记（已加入项目的视频显示 "✓" 标记）
- 添加按钮：将选中的文件写入 `videos.json`

### 5.2 项目创建流程

1. 输入项目名称
2. 选择项目目录（文件浏览器的目录选择模式）
3. 输入 output_dir（可选，默认不填则自动用 `<project_dir>/output`）
4. 创建完成，打开项目管理页

### 5.3 视频管理面板

项目内的"视频管理"选项卡:
- 显示当前已选视频列表
- 可勾选移除
- "浏览添加"按钮打开文件浏览器

## 6. 项目发现

不再依赖 `input_dir.parent` 扫描兄弟目录。UI 启动时:
1. 读取 `projects.json` 获取所有已知项目
2. 列表显示
3. 用户打开项目时，从 `project_dir` 加载 `project.yaml`

## 7. 迁移 (`python main.py migrate`)

### 7.1 范围

扫描以下来源:
- `projects.json` 中注册的所有项目
- 自动发现：`<config_dir>` 的子目录（包含 `project.yaml` 的）
- CLI 可选 `--from <path>` 指定要迁移的路径

### 7.2 流程

对每个检测到的旧项目:
1. 读取旧 `project.yaml`（在旧 project_dir = input_dir 内）
2. 提示用户指定新项目目录（默认推荐 `<app_root>/projects/<name>/`）
3. 扫描旧 input_dir 中所有视频，生成 `videos.json`
4. 复制 `project.yaml`、`project.json` 到新项目目录（`.vmeta`/`.vindex` 留在 `compressed_dir` 不动）
5. 更新新 `project.yaml`: 删除 `paths.input_dir`，更新 `paths.output_dir`（如为相对路径则转为绝对路径）
6. 更新注册表 `projects.json`（添加新条目，删除旧条目或标记旧位置）
7. 可选：备份旧 project.yaml 到 `project.yaml.bak` 后从旧位置删除

### 7.3 回滚

迁移前自动创建备份:
- 旧 `project.yaml` → `project.yaml.migrate-bak`
- 注册表 `projects.json` → `projects.json.migrate-bak`

## 8. CLI 接口变化

- 新增 `-p/--project` 参数，指向项目目录（包含 `project.yaml`）
- 保留 `-i/--input` 作为兼容别名，等价于 `-p`（迁移过渡）
- 保留 `-o/--output` 作为临时 output_dir 覆盖，但不再常用
- `serve` 命令从 `projects.json` registry 加载 `last_project`，不再需要 `-p`

```bash
python main.py analyze -p "C:/Users/me/vlog-projects/trip1"
python main.py serve         # 从 registry 加载 last_project
python main.py migrate        # 一键迁移旧项目
python main.py migrate --from "D:/GoPro/trip1"   # 指定路径迁移
```

## 9. 向后兼容

### 9.1 过渡期支持

迁移工具完成前，保留旧 `paths.input_dir` 支持:
- 如果 `project.yaml` 有 `paths.input_dir` 但无 `project_dir/videos.json`，降级为旧模式（扫 `input_dir`）
- 迁移后自动禁用降级

### 9.2 旧的 project.json

`project.json` 中如果包含 `name`、`currentDay`、`output_dir` 等字段，升级迁移时复制到新结构。

## 10. 实施阶段

### 阶段 1: 数据模型 + 视频加载器
- 修改 `ProjectPathsConfig` 删除 `input_dir`
- 创建 `_video_loader.py` 和 `videos.json` 支持
- 更新 `load_config` 和 `apply_run_paths`

### 阶段 2: 管道适配
- 将每个步骤中的 `find_videos(input_dir)` 替换为 `load_selected_videos(project_dir)`
- 调整 sidecar 文件位置逻辑

### 阶段 3: 注册表 + UI 项目管理
- 更新 `projects.json` 格式
- 修改 `project_service.py`/`server.py` 项目创建/发现逻辑
- 添加文件浏览器 API

### 阶段 4: 迁移工具
- 实现 `migrate` 命令
- 实现备份/回滚

### 阶段 5: 前端 UI
- 文件浏览器组件
- 视频管理面板
- 创建项目流程更新
- 注册表浏览更新

## 11. 测试重点

- `videos.json` 读写（`load_selected_videos` / `save_selected_videos`）
- 管道在不使用 `find_videos` 时依然能正确选择视频（用 `videos.json` 列表）
- `files` 参数在 `videos.json` 子集内过滤正确（`_matches_selected_stem`）
- sidecar `.vmeta`/`.vindex` 在 `compressed_dir` 中的读取（绝对路径不依赖 project_dir）
- 迁移工具对旧项目的正确处理 + 回滚流程
- UI 文件浏览的路径安全（防止遍历攻击）
- 现有测试修复：所有直接构造 `ProjectPathsConfig(input_dir=...)` 的测试改为构造 `output_dir` + 写入 `videos.json` fixture
- 前端改名回归：`currentProjectInputDir` → `currentProjectDir`、`config.input_dir` → `config.project_dir`，`run-input-dir` 输入框移除
