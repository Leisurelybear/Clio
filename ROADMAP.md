# Roadmap

需求追踪。每条需求拆成最小可执行 sub-task（per `AGENTS.md` §6.1 "一个功能一个 commit"），
完成时把 `[ ]` 改成 `[x]`，进行中用 `[~]`，阻塞用 `[!]`。

设计讨论 / 决策历史见 `AGENTS.md`，具体实现见 git log。

## 进行中

（暂无）

## 需求 R-004：UI 读取和编辑 config

**背景**：现在 UI 只读 paths（output_dir / compressed_dir / texts_dirs / scripts_dir / plans_dir / input_dir）
用于定位文件。要改 config 必须手开 `config.yaml` 改完再重启服务。
AI provider / context / tasks 切换在 UI 里完成能省一次重启外的来回。

**验收**：
- UI 新增「设置」tab（与 texts/voiceover/plan 并列）
- 显示完整 config 树：paths / ai.providers / ai.tasks / ai.context[_file] / compress / analyze 等所有 section
- 表单可改（dict 嵌套结构 → 嵌套 form）
- 改完点保存 → 写回 `config.yaml`（先 .bak 备份）→ 弹「需重启服务生效」提示
- 校验：路径是否存在、provider 名字是否注册、tasks.provider 是否引用已注册 provider
- 失败/重名校验不通过 → 表单内红字提示，不写文件

**子任务**：
- [x] R-004a：后端 `GET /api/config/raw` 返回 config 原始 dict；`PUT /api/config/raw` 校验并写回（带 .bak 备份）
- [x] R-004b：UI 加「设置」tab；渲染完整 config 为嵌套 form（dict / list / scalar）
- [x] R-004c：UI 表单编辑 + 保存（弹确认 → PUT → 提示重启 + 校验失败红字）
- [x] R-004d：文档：`vlog_tool/ui/README.md` 加「设置」tab 用法

## 需求 R-005：UI 化 analyze 流水线

**背景**：现在 `main.py analyze` 是 CLI（compress → analyze → voiceover → plan）。
要全跑流水线必须开终端。UI 化让「从把视频放进去到能编辑 AI 输出」一气呵成，
全部在浏览器里点完。

**验收**：
- UI 头部「运行」按钮 + 进度面板（弹窗 / 抽屉 / 新 tab，暂定 header 按钮 + 底部状态栏）
- 点按钮触发整条流水线（默认行为与 `main.py analyze` 一致）
- 每个 task × 每个 video 实时显示 `[i/N]` + ETA
- 跑完 / 出错有 toast 通知
- 不锁 texts/voiceover/plan tab 的编辑（同时打开也没问题）
- 进度数据存 `output/.progress.json`；UI 轮询读（2s 间隔）
- 走后台线程；UI 不能因为 analyze 卡住而冻结

**子任务**：
- [x] R-005a：`vlog_tool/progress.py` ProgressTracker：写 `output/.progress.json`（phase / current / total / message / started_at / eta / status）  ← `29bcb35`
- [x] R-005b：接入 `pipeline.run_analyze_all`：compress / analyze / voiceover / plan 关键节点调 `tracker.update`  ← `29bcb35`
- [x] R-005c：后端 `POST /api/run/start`（daemon 线程 + lock 防并发）；`GET /api/run/status` 读 `.progress.json`  ← `29bcb35`
- [x] R-005d：UI 头部「运行」按钮 + 进度面板（轮询 2s，渲染 phase / [i/N] / ETA / status）  ← `29bcb35`
- [x] R-005e：文档：`vlog_tool/ui/README.md` 加运行面板  ← `29bcb35`
- [x] R-005f：运行面板改 checkbox 选步骤，只跑选中步骤  ← `THIS_COMMIT`
- [x] R-005g：修复 ProgressTracker.done() 传参 bug  ← `THIS_COMMIT`

## 需求 R-001：UI 切换展示原视频 vs 压缩视频

**背景**：UI 现在只展示 `output/compressed/` 里的 640p 视频。想看 GoPro 4K 原片时没办法，
只能翻文件管理器 → 想加个 toggle 切到原片。

**验收**：
- 顶部 toggle：「压缩版 (640p)」/「原片 (4K)」
- 切到原片时，视频列表变成 `input_dir/*.mp4`（按 mtime 排序）
- 播放器能正常 seek / play 原片（Range 复用现有实现）
- 压缩版 ↔ 原片尽量按 basename 匹配，列表里能看到对应关系

**子任务**：
- [x] R-001a：后端 `/api/videos?source=compressed|original` 支持双来源  ← `88679ee`
- [x] R-001b：后端 `/api/video?source=original` 从 `input_dir` 拉原片  ← `88679ee`
- [x] R-001c：UI 顶部加 source toggle，切换时重新拉列表  ← `f1d09ac`
- [x] R-001d：`vlog_tool/ui/README.md` 加 toggle 说明 + 边角 case 文档  ← `ec83f48`
- [x] R-001e：边角：原片没有 `001_` 这样的 index 前缀；UI 用 basename 匹配压缩版，列表里标出哪些匹配上哪些没  ← 拆到 `88679ee`（后端 helper）+ `f1d09ac`（UI match-badge）

## 需求 R-006：UI 侧栏分层（项目级 vs 视频级）

**背景**：现在右栏三个 tab（texts / voiceover / plan）同级，但 plan 跨视频
（引用 `sequence[].index`），texts/voiceover 是 per-video。层级不对：
plan 是项目级产物，texts/voiceover 是视频级产物。提前把 sidebar 做成两级
导航，让 R-004（设置）和 R-005（运行）也有自然的位置。

**验收**：
- sidebar 分两段：上面「项目」section，下面「视频」section
- 项目 section 三个入口：`📋 Plan (day1)` / `⚙ 设置`（R-004，未做 → 灰显带 tooltip）/ `▶ 运行`（R-005，未做 → 灰显带 tooltip）
- 视频 section 保持原样（match 角标 + 计数）
- 选 video → 右栏 texts/voiceover tab（去掉 plan tab）
- 选 plan → 右栏隐藏 tab bar，整块渲染 plan 面板 + 保存按钮
- 选 plan 时 player 保持上一个选中的视频；点 plan 的 segment 仍正常跳转到对应视频 + 时间
- 灰显入口：`opacity: 0.4; cursor: not-allowed;` + `title="待 R-004 / R-005 实现"`

**子任务**：
- [x] R-006a：`vlog_tool/ui/static/index.html` + `style.css`：sidebar 两段结构 + 灰显样式  ← `a648e60`
- [x] R-006b：`vlog_tool/ui/static/app.js`：state.currentEntity + selectPlan + 右栏内容分发；plan 内容从 tab 拆出来作为独立渲染分支  ← `c42d347`
- [x] R-006c：`vlog_tool/ui/README.md`：界面布局图更新 + 项目级 section 说明  ← `778c44a`
- [!] R-006d：规划视图切源时，播放器应自动切换到新源的对应视频（而非清空）。当前行为：`setSource` 在 plan 分支只清播放器 —— 用户需再点击左侧视频或 plan segment 才加载。预计修复：在 plan 分支用 `state.currentVideo?.index` 在新 `state.videos` 里查找对应文件并调 `playVideoSegment`。

## 需求 R-007：UI 多项目切换

**背景**：当前 UI 锚定一个 `output_dir`，想看另一个 vlog 项目必须改 `config.yaml` 后重启服务。
用户期望在页面上切换项目，直接查看其他项目的视频列表和 AI 解析结果。

**验收**：
- UI 顶部/侧栏显示当前项目名，可点击切换
- 切换后刷新视频列表 + 编辑内容（texts / scripts / plan 全部切到新项目的文件）
- 无需重启服务
- 新项目可在 UI 中创建：输入项目名 + 素材目录 → 自动建项目目录、生成 project.json → 刷新切换
- 空项目引导：视频列表为空时显示空状态 + 素材目录路径提示

**子任务**：
- [x] R-007a：后端 `/api/projects` 列出所有 `project.json` 所在目录（含 steps 检测）  ← `THIS_COMMIT`
- [x] R-007b：后端 `/api/project/create` 新建项目（目录名安全化 + project.json 初始化）  ← `THIS_COMMIT`
- [x] R-007c：侧栏项目选择器（下拉框）+ 新建项目模态框  ← `THIS_COMMIT`
- [x] R-007d：URL `?project=name` 切换项目，页面重载自动加载新项目数据  ← `THIS_COMMIT`
- [x] R-007e：空视频列表空状态引导（显示素材目录路径）  ← `THIS_COMMIT`

## 需求 R-008：UI 单步执行 + 文件夹/文件选择

**背景**：当前 UI 只能看已有产物，要重新跑某个步骤（compress / analyze / voiceover / plan）
必须开终端。用户期望在 UI 上选文件夹→选视频→点按钮→跑完看结果，不用切到命令行。

**验收**：
- 侧栏「▶ 运行」启用，作为 R-008 入口
- 右栏显示运行面板：可选择步骤（compress / analyze / voiceover / plan / 全部）
- 可单独选择输入目录（不限于 config 里的 `input_dir`，可手动输入路径或浏览选择）
- 可在所选目录下勾选要处理的文件（而非全部跑）
- 点击执行后面板显示实时进度 + ETA（复用 R-005 的 `.progress.json` 或直接 SSE）
- 跑完后自动切到对应视图（如跑完 voiceover 切到口播 tab 刷新）

**子任务**：
- [ ] R-008a：后端 `/api/run/step` 端点，接受 `{ step: string, input_dir?: string, files?: string[] }`
- [ ] R-008b：运行面板 UI（步骤选择、进度、结果查看）
- [ ] R-008c：输入目录选择 + 文件勾选交互
- [ ] R-008d：跑完后自动刷新对应视图
- [ ] R-008e：文档 + 侧栏「运行」入口启用

> **F-001 建议**：外部分析建议 R-007（多项目切换）与 R-008（单步执行）合并为统一「项目管理 + 流水线」面板，用 `projects.json` 持久化项目列表。实现时可直接合并实施。

## 需求 R-009：工程健壮性

**背景**：当前项目在依赖管理、跨平台兼容、代码测试方面存在短板。
固定依赖版本 + 补充 `setup.sh` + 为核心纯函数加单元测试。

**验收**：
- ✅ `requirements.txt` 锁定所有依赖版本（`requirements-locked.txt`）
- ✅ 核心纯函数有单元测试（128 用例，GitHub Actions CI）
- [ ] 补充 Linux/macOS 的 `setup.sh`（与现有 `setup.ps1` 等效）
- [ ] `main.py check` 对 venv 检测兼容 Linux `bin/` 和 Windows `Scripts/`

**子任务**：
- [x] R-009a：锁依赖版本 + 迁移指南
- [ ] R-009b：Linux `setup.sh`
- [x] R-009c：核心纯函数单元测试（pytest，128 用例，CI 自动跑）
- [ ] R-009d：venv 检测跨平台修复（B-007）

## 需求 R-010：AI 输出质量

**背景**：AI 分析结果偶尔有误（地点误判、时间轴不准、遗漏亮点），
且用户无法干预 prompt 细节。支持外部 prompt 覆盖 + 置信度评分 + 多模型对比。

**验收**：
- 支持外部 prompt 文件覆盖系统默认 prompt（`templates/prompts/` 目录下同名文件）
- analyze/texts 输出增加 `_confidence` 字段（AI 自评置信度）
- CLI 支持对同一视频用多个模型分析并对比结果

**子任务**：
- [ ] R-010a：外部 prompt 文件覆盖机制
- [ ] R-010b：置信度评分（修改 prompts 让 AI 输出 `_confidence`）
- [ ] R-010c：多模型对比 CLI

## 需求 R-002：一键剪辑（从 plan 切出所有片段）

**背景**：`plan.json` 的 `sequence[]` 已经给好了 `use_timeline` 范围，用户要在剪映里手动剪 →
想一键 ffmpeg 切完，输出到指定目录，含进度。

**验收**：
- 新 CLI 子命令 `cut`，不依赖 UI
- 读 `plans/day<N>_plan.json`
- 对 sequence[] 每条用 ffmpeg `-ss <start> -to <end>` 切
  - 默认 `-c copy`（快，几秒切完一段）；提供 `--reencode` 选 h264 精确剪
- `--output <dir>` 选保存目录（默认 `output/cuts/<day>/`）
- 输出：切好的 `.mp4` + 对应 texts JSON 复制到同目录
- 进度：`[i/N] 切割 002 (01:00-01:15)...` + 剩余 ETA
- 完成时生成 `manifest.md`：每条 sequence 列出输出文件 / 时间范围 / 标题

**子任务**：
- [x] R-002a：`vlog_tool/cut.py`：`cut_one(video, start, end, out, *, reencode=False)` 包装 ffmpeg
- [x] R-002b：`vlog_tool/cut.py`：`parse_time_range("00:00-00:20")` 复用 utils 已有逻辑
- [x] R-002c：`pipeline.py`：`run_cut_all(config, day, output_dir, reencode=False)` + 进度
- [x] R-002d：`main.py`：`cut` 子命令（`--day`, `--output`, `--reencode`）
- [x] R-002e：配套 texts JSON 复制到 `cuts/<day>/`（重命名 `001_xxx_seg_03.json`）
- [x] R-002f：进度走 `timed()` + `[i/N]` + ETA（与现有 pipeline 一致）
- [x] R-002g：生成 `manifest.md`（markdown 表格：# / 视频 / 时间 / 输出文件 / 标题）
- [x] R-002h：文档：`README.md` 加 `cut` 子命令

## 需求 R-003：选择式 compress / analyze / refine

**背景**：现在要重做某个视频的口播必须重跑整个 pipeline；想：
- 选单个视频做 compress / analyze / texts / voiceover
- 重新生成某一段（e.g. "只重做 002 的 voiceover"）
- 给某条文本加临时 context 定向润色（不污染全局 `ai.context`）

**验收**：
- CLI：`analyze -i single.mp4` 已有 → 审计并补缺
- CLI：`voiceover -i single.json` 缺 → 加
- CLI：`refine --context "临时说明"` 新增，临时拼到 prompt（优先级高于 `ai.context`）
- UI：视频列表每项 dropdown「重跑 texts / voiceover / 全部 / 标记 refine」
- UI：refine tab 加临时 context textarea

**子任务**：
- [x] R-003a：审计现有子命令的 `-i` 单文件支持（`compress` / `analyze` / `scripts` / `plan` / `refine`）
- [x] R-003b：补上 `scripts` 的 `-i` 单 JSON 支持 + `compress`/`analyze` 单文件支持
- [x] R-003c：`refine --context "..."` 参数：临时追加到 prompt，写在 `ai.context` 之后
- [x] R-003d：UI 视频列表每项加 dropdown「重跑 texts / voiceover / 全部」
- [x] R-003f：后端 `POST /api/rerun` 接受 `{video, task, source}`
- [ ] R-003e：UI refine tab 加临时 context textarea（延后单独做）
- [ ] R-003g：pipeline `run_rerun_single`（已有单文件支持，无需独立函数）

## 暂存 / WIP

- （暂无）

## 文档维护（来自 2026-06-10 全面 review）

| ID | 问题 | 说明 | 状态 |
| --- | --- | --- | --- |
| D-001 | AGENTS.md §7 commit 列表过期 | 最后一条是 R-007，缺 6 个新 commit | ✅ 已更新 |
| D-002 | vlog_tool/ui/README.md 运行状态描述过期 | "▶ 运行灰显（待 R-005 实现）" — R-005 已完成 | ✅ 已修复 |
| D-003 | README.md / README.en.md 未提 per-project 配置 | `project.yaml` 分层配置功能未写入用户文档 | ✅ 已补充 |
| D-004 | config.example.yaml model 名与实际使用不符 | example 写 `deepseek-chat`，config.yaml 用 `deepseek-v4-flash`，应备注说明 | ✅ 已加注释 |

## 架构改进（来自 review，与设计文档 Phase 1 对齐）

| ID | 问题 | 说明 |
| --- | --- | --- |
| A-001 | server.py → 989 行单一闭包 | 拆 routes/ + services.py（设计文档 Phase 1b） |
| A-002 | app.js → 1076 行全局函数 | 拆 state.js / api.js / viewer.js（设计文档 Phase 1c） |
| A-003 | `_write_text_file` / `_rewrite_text_file` 80% 重复 | 提取公共函数 |
| A-004 | `updateEntityUI` 四个几乎相同的分支 | 用一个 selector 统一处理 |
| A-005 | `project.json` output_dir 和 `project.yaml` paths.output_dir 不同步 | 两份配置来源不一致，应统一或互相感知

## 已知问题（Bug Tracker）

按优先级 P0（立即）→ P1（近期）→ P2（中期）→ P3（长期）排列。

### P0 — 立即修复

| ID | 问题 | 修复思路 | 状态 |
| --- | --- | --- | --- |
| B-001 | Gemini Files API 上传视频后未清理，耗尽配额 | `try/finally` 确保视频上传后请求删除 | ✅ `a9996a9` |
| B-002 | with_retry 重试时重复上传同一视频 | 把上传移出重试逻辑，上传不重试 | ✅ `a9996a9` |
| B-003 | 临时文件残留（中断时 .tmp 文件未被自动清理） | 改用 `with` 语句或 `try/finally` 清理 | ✅ `0533051` |
| B-012 | `_run()` 静默吞异常 — pipeline 失败 UI 无感知 | `except Exception: pass` → 写 progress.json error 状态 + 打印日志 | ✅ `9c73903` |
| B-013 | `apply_run_paths` 直接修改入参 config 对象 | 返回新 config 或 `copy.deepcopy()` 再修改 | ✅ `9c73903` |
| B-014 | `requirements.txt` 无版本号 — breaking change 风险 | `pip freeze` 锁版本，参考 R-009a | ✅ `requirements-locked.txt` |

### P1 — 近期

| ID | 问题 | 修复思路 | 状态 |
| --- | --- | --- | --- |
| B-004 | ETA 估算偏低（成功项包含了失败项的时间） | 耗时统计移入 `finally` 块，只算成功项 | |
| B-007 | venv 跨平台检测只认 Windows `Scripts/`，Linux 是 `bin/` | 同时兼容 `bin/` 和 `Scripts/` | |
| B-015 | `project.yaml` 写入时只做了 YAML 格式校验，未跑 `_validate_config` | `do_PUT /api/config/raw?project=X` 写前做完整合并校验 | ✅ `9c73903` |
| B-016 | `config.yaml` 里 `deepseek-v4-flash` 可能是无效模型名（AGENTS §8.4） | 确认实际可用模型名，更新 config 或加备注 | 🆕 |

### P2 — 中期

| ID | 问题 | 修复思路 | 状态 |
| --- | --- | --- | --- |
| B-005 | Linux 下 `sorted(Path.iterdir())` 顺序不保证（glob 也不保证顺序） | 显式 `sorted()` 后再匹配 | |
| B-008 | 函数隐式修改入参（如 `analyze_video` 等修改传入的 dict 字段） | 入参 `deepcopy()` 避免副作用 | |
| B-017 | `_find_texts_dirs` 匹配 `texts*` 太宽 — `texts_backup` 也会匹配 | 用更精确的 glob 或加排除规则 | 🆕 |
| B-018 | `_config_cache` 只增不减（仅在 PUT config 时 pop） | 项目列表刷新时清理失效缓存 | 🆕 |

### P3 — 长期

| ID | 问题 | 修复思路 | 状态 |
| --- | --- | --- | --- |
| B-009 | AI 偶尔输出非纯 JSON，`extract_json` 解析失败 | 更精准提取合法 JSON（递归剥离 markdown） | |
| B-011 | 新用户 `python main.py check` 误判失败（提示不够友好） | 优化 check 步骤提示信息 | |
| B-010 | （待进一步确认） | — | |
| B-019 | `VIDEO_EXTS` 重复定义（utils.py 含 .avi/.mkv，server.py 没有） | 移到 `vlog_tool/_constants.py` 统一引用 | 🆕 |
| B-020 | `_write_csv` 中 `format_index(rec.index, 3)` 硬编码 `3` 而非使用 config | 改用 `config.naming.index_width` | 🆕 |

## 性能优化

| ID | 瓶颈 | 优化方案 | 优先级 |
| --- | --- | --- | --- |
| P-001 | `pipeline.py` 中视频压缩与 AI 分析串行执行，耗时久 | `ThreadPoolExecutor` 并行执行压缩 + AI 分析 | P2 |
| P-002 | 重复调用 ffprobe 读取同一视频的 `duration_sec` / `size_mb` | 缓存已读取信息，复用结果 | P3 |
| P-003 | `GET /api/videos` 每次遍历目录 I/O 开销大 | 加目录 mtime 缓存，复用未变更的扫描结果 | P3 |

## 已完成（最近，按时间倒序）

| Commit | 简述 |
| --- | --- |
| `b6b84df` | test: progress.py unit tests (12 tests) |
| `23e30e5` | test: log.py and cut.py unit tests (38 tests) |
| `a2a5d66` | test: comprehensive utils.py unit tests (34 tests) |
| `66613cc` | test: comprehensive config.py unit tests (34 tests) |
| `9ade769` | test: add test infrastructure and GitHub Actions CI |
| `80e83ec` | fix(ui): fall back to global config when project has no project.yaml |
| `41ba068` | fix: address review findings - gemini cleanup scope + project config validation |
| `d785643` | chore: add local state files to .gitignore |
| `d6d62ef` | feat(config): per-project configuration via project.yaml (deep-merge + _get_config cache) |
| `0533051` | fix(ui): prevent temp file leak on interrupt (B-003) |
| `a9996a9` | fix(ai): clean up Gemini File API uploads + move upload out of retry (B-001, B-002) |
| `a93b5f5` | R-004 UI 配置编辑（后端 raw config API / 递归嵌套表单 / 校验 + .bak 保存 / 文档） |
| `6706dc3` | R-002 CLI 裁剪（cut.py + run_cut_all + 子命令 + manifest.md + 文档） |
| `f3fc932`..`2ad23f5` | R-002 UI 裁剪（POST /api/cut + sidebar 裁剪 tab + cut 表单 + 进度提示） |
| `0d52cf6`..`439911c` | 本地 Web UI（拆 6 commit：backend / CLI / frontend / docs / plan-seek fix / AGENTS 同步） |
| `88679ee` `f1d09ac` `ec83f48` | R-001 UI 源切换（后端双 source / 顶部 toggle + match 角标 / README 文档） |
| `a648e60` `c42d347` `778c44a` | R-006 sidebar 分层（HTML+CSS / JS state machine / README 布局图） |
| `a2597f0` | 删 plan tab 跳转 bug |
| `25128d1` | AI 调用加重试与退避 |
| `835b7e9` | 配置加载时校验 proxy / tasks |
| `b503c9c` | 日志助手 `format_size` / `format_duration` / `timed` |
| `3d39b6a` | 未捕获异常整成一条 ERROR 日志 |
| `9d5b393` | ffmpeg / AI 详细日志 + ETA 进度 |
| `19e9b8e` | 删孤立的 `video_analysis.py` |
| `3a2ca76` | `extract_json` 从 `ai/gemini.py` 移到 `utils.py` |
| `d98b233` | AGENTS.md refresh（--fix, log helpers） |
