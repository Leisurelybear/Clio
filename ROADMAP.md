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
- [x] R-005b：接入 `pipeline.run_analyze_all`：compress / analyze / scripts / plan / label 关键节点调 `tracker.update`  ← `29bcb35`
- [x] R-005c：后端 `POST /api/run/start`（daemon 线程 + lock 防并发）；`GET /api/run/status` 读 `.progress.json`  ← `29bcb35`
- [x] R-005d：UI 头部「运行」按钮 + 进度面板（轮询 2s，渲染 phase / [i/N] / ETA / status）  ← `29bcb35`
- [x] R-005e：文档：`vlog_tool/ui/README.md` 加运行面板  ← `29bcb35`
- [x] R-005f：运行面板改 checkbox 选步骤，只跑选中步骤  ← `a8daa63`
- [x] R-005g：修复 ProgressTracker.done() 传参 bug  ← `a8daa63`

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
- [x] R-007a：后端 `/api/projects` 列出所有 `project.json` 所在目录（含 steps 检测）  ← `c91dc6d`
- [x] R-007b：后端 `/api/project/create` 新建项目（目录名安全化 + project.json 初始化）  ← `c91dc6d`
- [x] R-007c：侧栏项目选择器（下拉框）+ 新建项目模态框  ← `c88549e`
- [x] R-007d：URL `?project=name` 切换项目，页面重载自动加载新项目数据  ← `c88549e`
- [x] R-007e：空视频列表空状态引导（显示素材目录路径）  ← `c88549e`

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
- ✅ 核心纯函数 + 路由 handler + 编排逻辑有单元测试（**381 用例**，GitHub Actions CI）
- [ ] 补充 Linux/macOS 的 `setup.sh`（与现有 `setup.ps1` 等效）— 项目主要面向 Windows
- [ ] `main.py check` 对 venv 检测兼容 Linux `bin/` 和 Windows `Scripts/`

**子任务**：
- [x] R-009a：锁依赖版本 + 迁移指南
- [ ] R-009b：Linux `setup.sh`（低优先级，项目主要面向 Windows）
- [x] R-009c：核心纯函数 + 路由 + 编排单元测试（pytest，381 用例，CI Linux + Windows 双平台）
- [ ] R-009d：venv 检测跨平台修复（B-007，影响 Linux CI）

## 需求 R-010：AI 输出质量与 Prompt 管理

**背景**：AI 分析结果偶尔有误（地点误判、时间轴不准、遗漏亮点），
且用户无法干预 prompt 细节。支持外部 prompt 覆盖 + 置信度评分 + 多模型对比 + UI 编辑 prompt。

**验收**：
- 支持外部 prompt 文件覆盖系统默认 prompt（`templates/prompts/` 目录下同名文件，改 prompt 无需改代码）
- UI 设置 tab 增加「Prompt 管理」面板：列出所有系统 prompt（analyze / voiceover / plan / refine 等）
- 每个 prompt 可在线编辑、恢复默认、保存到项目级 `project.yaml` 或全局覆盖
- 保存后下次 AI 调用自动使用修改后的 prompt
- analyze/texts 输出增加 `_confidence` 字段（AI 自评置信度）
- CLI 支持对同一视频用多个模型分析并对比结果

**子任务**：
- [ ] R-010a：外部 prompt 文件覆盖机制（`templates/prompts/` 同名文件优先）
- [ ] R-010b：置信度评分（修改 prompts 让 AI 输出 `_confidence`）
- [ ] R-010c：多模型对比 CLI
- [ ] R-010d：后端 `GET /api/prompts` 返回所有可用 prompt；`PUT /api/prompts/{name}` 保存覆盖
- [ ] R-010e：UI 设置 tab 内嵌 Prompt 管理面板（列表 + 编辑器 + 恢复默认）

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

## ✅ 需求 R-011：规划面板预览播放

**背景**：当前规划面板只能看到 segment 列表，点击单个 segment 跳到对应时间。
无法快速预览整个编排方案的连贯播放效果。

**验收**：
- 规划面板新增「▶ 预览播放」按钮
- 点击后遍历 sequence[] 依次播放每个 segment
- 每个 segment 按 `use_timeline` 的 start 时间跳转，播到 end 时间后自动推进到下一个
- 当前播放的 segment 在列表中高亮
- 面板显示播放进度（Segment 3/11）
- 支持「■ 停止预览」随时终止
- 预览结束后自动停止，播放器停在最后一个 segment

**子任务**：
- [x] R-011a：前端 state 加 previewActive / previewIndex / _previewEndTime
- [x] R-011b：renderPlan 加预览按钮 + 高亮当前 segment
- [x] R-011c：startPreview / stopPreview / _playPreviewSegment 控制逻辑
- [x] R-011d：player.ontimeupdate + onended 接入预览自动推进

## ✅ 需求 R-012：预览进度条与交互控制

**背景**：R-011 实现了 segment 自动跳转播放，但用户无法看到整体进度，也无法手动跳到某个 segment。

**验收**：
- 预览模式下在视频播放器下方显示进度条（表示整个 sequence），显示当前 segment 位置
- 进度条可点击拖动跳到对应 segment
- 预览控制栏显示：上一步 / 播放暂停 / 下一步 / 当前 segment 名称
- 手动拖动播放器进度条时暂时不触发自动推进（防止误拖导致跳段）

**子任务**：
- [x] R-012a：预览控制栏 UI（上一步 / 暂停 / 下一步 + segment 名称 + 整体进度条）
- [x] R-012b：进度条点击/拖动切换到对应 segment
- [x] R-012c：手动拖动播放器进度时不触发自动推进

## ✅ 需求 R-013：离线语音识别（Whisper ASR → 转录 → 口播参考）

**背景**：当前口播文案完全基于视频画面分析生成（地点、动作、时间轴），但无法知道视频中的人物说了什么。离线 whisper 转录提供语音内容作为口播计划上下文。

**验收**（全部 ✅）：
- ✅ 新增 pipeline 步骤 `transcribe`（compress → analyze → **transcribe** → voiceover → plan）
- ✅ 离线 faster-whisper 转录，原始视频绝对时间轴，split 段通过 `offset_sec` 换算
- ✅ CLI 子命令 `transcribe` / `whisper install` / `whisper check`
- ✅ UI 转录 tab + delete/edit/seek + 每视频 rerun + 10% 进度
- ✅ CUDA 自动检测 + CPU 回退（`cublas64_12.dll` 缺失处理）
- ✅ 独立依赖 `requirements-whisper.txt`，不污染主依赖，惰性导入

**子任务**：
- [x] R-013a：WhisperConfig dataclass 与模型枚举（Task 1, `f4b84e0`）
- [x] R-013b：核心转录模块（Task 2, `7263367`）
- [x] R-013c：pipeline 步骤 `run_transcribe_all`（Task 3, `90da4b3`）
- [x] R-013d：CLI 子命令 `transcribe` / `whisper`（Task 4, `d2e3924`）
- [x] R-013e：transcript 注入 PLAN_PROMPT（Task 5, `ef7b033`）
- [x] R-013f：libs.whisper.package 等配置反序列化（Task 6, `370516c`）
- [x] R-013g：UI 后端 transcript/whisper 路由（Task 7, `4b1c6e6`）
- [x] R-013h：UI 前端 transcripts tab / sidebar badge / run step（Task 8, `bcfbe04`）
- [x] R-013i：CUDA 回退 CPU + 惰性导入 + 无 torch 依赖（`1d1b46a`, `1c5d681`）
- [x] R-013j：综合修复：rerun 404, UI 显示/seek/delete, 10% 进度, offset_sec 换算（`1b53499`）

## 需求 R-014：AI 模型 Token 用量统计（项目级别）

**背景**：目前所有 AI 调用只打印 prompt 大小和响应大小（字节），没有按 token 统计。用户不知道每个项目消耗了多少 token，也无法对比不同模型的成本。项目级别的 token 统计有助于优化模型选择和成本控制。

**验收**：
- 每次 AI 调用后记录 token 用量（prompt_tokens / completion_tokens / total_tokens），写入 `output/.token_usage.json`
- 如果模型 API 未返回 token 数，使用 tiktoken 估算
- 按项目归总：记录每个项目下各模型的累计 token 数
- UI 设置 tab 或新 tab 显示 token 统计（项目总览 / 各模型占比 / 按时间）
- CLI 支持 `main.py tokens` 查看统计

**子任务**：
- [ ] R-014a：后端 AI 调用统一封装 token 记录（不论 provider 都返回 token 数）
- [ ] R-014b：写入 `output/.token_usage.json`，按项目/模型/日期聚合
- [ ] R-014c：UI 显示 token 统计面板
- [ ] R-014d：CLI `tokens` 子命令

## 需求 R-015：配置热重载

**背景**：当前 UI 保存 `config.yaml`（全局配置）后缓存未失效，必须重启服务才能生效。
`project.yaml` 保存时虽然会弹出缓存，但前端始终显示"需重启服务生效"。
外部（CLI / 文本编辑器）修改配置文件也完全不被检测。调研见 `docs/superpowers/specs/2026-06-13-config-hot-reload-audit.md`。

**验收**：
- 全局 `config.yaml` 保存后清理 `_config_cache`
- 项目级保存后区分提示（不再统一显示"需重启服务生效"）
- `_get_config()` 增加 mtime 检查，文件变更时自动重新读取
- 限制 `_config_cache` 大小上限

**子任务**：
- [x] R-015a：`POST /api/config/raw` 全局保存后调 `_config_cache.clear()` ← `e21373e`
- [x] R-015b：`_get_config()` 加 mtime 缓存失效
- [ ] R-015c：前端区分项目级 vs 全局保存提示信息
- [x] R-015d：`_config_cache` 添加 maxsize 限制（LRU cap 20） ← `e21373e`

## 暂存 / WIP

- （暂无）

## 需求 R-016：可拖拽调整 UI 布局

**背景**：当前 UI 三栏布局（侧栏 / 播放器 / 编辑区）宽高固定，无法适应不同屏幕尺寸或用户偏好。

**验收**：
- 侧栏、播放器、编辑区之间的分割线可拖拽调整宽度
- 播放器区域高度可拖拽调整
- 布局状态持久化到 `project.json` 或 localStorage

## 需求 R-017：Plan 面板时间轴拖拽浏览

**背景**：当前 plan 面板只显示 segment 列表，点击跳转视频。用户期望在时间轴上拖拽查看不同 segment 对应的视频内容。

**验收**：
- Plan 面板顶部显示整体时间轴（表示 plan 的 sequence[]）
- 每个 segment 在时间轴上以不同颜色的区块显示
- 用户可拖拽时间轴上的滑块/点击区块来跳转到对应 segment
- 时间轴同步：预览播放时时间轴高亮跟随当前 segment

## 需求 R-018：视频多选 + 选定步骤执行

**背景**：当前运行面板可以选步骤、跑全部视频，或 rerun 单个视频。缺少「勾选多个视频 → 选步骤 → 只跑选中视频」的交互。用户期望在侧栏勾选任意视频后，点击运行只处理选中项。

**验收**：
- 侧栏视频列表每项前加 checkbox，支持多选
- 顶部显示「已选 N/N」+「全选/取消全选」
- 运行面板步骤 checkbox 保持不变，但「运行」按钮联动选中视频
- 未选任何视频时运行按钮禁用，显示「请先选择视频」
- 运行进度只反映选中视频的处理进度
- 选中视频在列表中高亮显示

**子任务**：
- [ ] R-018a：侧栏视频列表加 checkbox + 全选/取消全选
- [ ] R-018b：后端 `/api/run/start` 支持 `files: string[]` 过滤参数
- [ ] R-018c：运行面板根据选中视频调整进度显示（总数 / ETA / message）
- [ ] R-018d：选中视频高亮样式 + 计数
- [ ] R-018e：空选择时禁用运行按钮 + 提示文案

## 文档维护（来自 2026-06-10 全面 review）

| ID | 问题 | 说明 | 状态 |
| --- | --- | --- | --- |
| D-001 | AGENTS.md §7 commit 列表过期 | 最后一条是 R-007，缺 6 个新 commit | ✅ 已更新 |
| D-002 | vlog_tool/ui/README.md 运行状态描述过期 | "▶ 运行灰显（待 R-005 实现）" — R-005 已完成 | ✅ 已修复 |
| D-003 | README.md / README.en.md 未提 per-project 配置 | `project.yaml` 分层配置功能未写入用户文档 | ✅ 已补充 |
| D-004 | config.example.yaml model 名与实际使用不符 | example 写 `deepseek-chat`，config.yaml 用 `deepseek-v4-flash`，应备注说明 | ✅ 已加注释 |

## 架构改进（来自 review，与设计文档 Phase 1 对齐）

| ID | 问题 | 说明 | 状态 |
| --- | --- | --- | --- |
| A-001 | server.py → 1261 行单一闭包 | 拆 routes/ + services/（Phase 1c 完成，454 行） | ✅ |
| A-002 | app.js → 1509 行全局函数 | 拆 src/ ES 模块（Phase 1d 完成，8 个模块） | ✅ |
| A-003 | pipeline.py → 789 行堆叠 | 拆 tasks/ 包（Phase 1b 完成，96 行） | ✅ |
| A-004 | `_write_text_file` / `_rewrite_text_file` 80% 重复 | 提取公共函数（Phase 1b 已移入 _helpers.py） | ✅ |
| A-005 | `project.json` vs `project.yaml` 不同步 | 两份配置来源不一致，应统一或互相感知 | 🔴 |
| A-006 | 前端 ES module 动态 import 循环引用 | viewer/editor/runner 三方存在动态 import，长期可重构 | 🟡 |

## 已知问题（Bug Tracker）

按优先级 P0（立即）→ P1（近期）→ P2（中期）→ P3（长期）排列。

### 代码审查发现（2026-06-16，5 路平行 subagent）

| ID | 优先级 | 问题 | 状态 |
| --- | --- | --- | --- |
| C1 | P0 | POST /api/rerun path traversal — video_basename 未校验 | ✅ `41abe5b` |
| C2 | P0 | Empty-state 按钮不刷新视频列表 | ✅ `89614a4` |
| C3 | P0 | playVideoSegment addEventListener 泄漏 | ✅ `bce09ce` |
| C4 | P0 | OpenAI 4xx 被静默重试 | ✅ `dba1cd9` |
| C5 | P0 | YAML 未知字段→dataclass TypeError 崩溃 | ✅ `18ccee4` |
| C6 | P0 | Provider HTTP 连接泄漏 | ✅ `71659aa` + `ef68308` |
| I1 | P1 | 转录编辑 onblur 竞态 | ✅ `fe511be` |
| I2 | P1 | save() 数据引用竞态 | ✅ `8d3b2f8` + `bebf21f` |
| I3 | P1 | startRun 双击启动两条流水线 | ✅ `1406e0e` |
| I4 | P1 | Portal 菜单事件监听器泄漏 | ✅ `08d815c` |
| I5 | P1 | Range 请求不支持 bytes=-N 后缀 | ✅ `d2591a9` |
| I6 | P1 | POST /api/cut day_label 路径穿越 | ✅ `b072240` |
| I7 | P1 | 硬编码 G:/ffmpeg | ✅ `74c34f5` |
| I8 | P1 | _resolve_original 无下划线 stem 的 ValueError 崩溃 | ✅ `e6e7666` |
| I9 | P1 | run_ffmpeg stdout pipe 死锁 | ✅ `9288216` |
| I10 | P1 | CLI 不加载 project.yaml 覆盖 | ✅ `60d765f` |
| I11 | P1 | _TeeWriter.__getattr__ 暴露原始 stdout/stderr 的 close/writelines | ✅ `947a320` |
| I12 | P1 | openai_compat 重试次数硬编码 | ✅ `ef2311d` + `ef68308` |
| M1~M36 | P2 | Minor issues — 见 `docs/review/2026-06-16-feat-whisper-full-audit.md` | 🆕 |

### P0 — 立即修复

| ID | 问题 | 修复思路 | 状态 |
| --- | --- | --- | --- |
| B-001 | Gemini Files API 上传视频后未清理，耗尽配额 | `try/finally` 确保视频上传后请求删除 | ✅ `a9996a9` |
| B-002 | with_retry 重试时重复上传同一视频 | 把上传移出重试逻辑，上传不重试 | ✅ `a9996a9` |
| B-003 | 临时文件残留（中断时 .tmp 文件未被自动清理） | 改用 `with` 语句或 `try/finally` 清理 | ✅ `0533051` |
| B-012 | `_run()` 静默吞异常 — pipeline 失败 UI 无感知 | `except Exception: pass` → 写 progress.json error 状态 + 打印日志 | ✅ `9c73903` |
| B-013 | `apply_run_paths` 直接修改入参 config 对象 | 返回新 config 或 `copy.deepcopy()` 再修改 | ✅ `9c73903` |
| B-014 | `requirements.txt` 无版本号 — breaking change 风险 | `pip freeze` 锁版本，参考 R-009a | ✅ `requirements-locked.txt` |
| B-021 | `cut.py:51` ffmpeg 用了 `-to` 语义上应为 `-t`（指定时长） | 改 `-to duration_sec` → `-t duration_sec` | ✅ `fix/B-021-cut-to-to-t` |
| B-022 | `project_service.py:52` `_detect_steps` 中 `any(t.iterdir() for t in texts)` — iterdir() 生成器永远为 truthy，空目录也被判为 analyze 已完成 | 改成 `any(any(True for _ in t.iterdir()) for t in texts)` | ✅ `fix/B-022-detect-steps-empty-dir` |
| B-023 | `routes/projects.py` 创建/写入 project.json 用 `write_text()` 绕过 `_save_atomic`，崩溃留损坏文件 | 改用 `_save_atomic` | ✅ `fix/B-023-project-json-atomic` |
| B-053 | `sidebar.js:pollRerunStatus` `statusEl`/`fill`/`logsEl` 在早期 `return` 前未声明，触发 ReferenceError | 变量声明提升到 `return` 之前 | ✅ `c283bb9` |
| B-061 | `config_routes.py` 全局 config 保存后 `_config_cache` 未失效，新配置无效直到重启 | 写盘后调 `_config_cache.clear()` | ✅ `e21373e` |
| B-062 | `tasks/analyze.py` `glob("*.mp4")` 仅匹配 `.mp4`，丢失 `.mov`/`.m4v` 等视频格式 | 替换为 `VIDEO_EXTS` 过滤 | ✅ `51f50d7` |

### P1 — 近期

| ID | 问题 | 修复思路 | 状态 |
| --- | --- | --- | --- |
| B-004 | ETA 估算偏低（成功项包含了失败项的时间） | 耗时统计移入 `finally` 块，只算成功项 | |
| B-007 | venv 跨平台检测只认 Windows `Scripts/`，Linux 是 `bin/` | 同时兼容 `bin/` 和 `Scripts/` | |
| B-015 | `project.yaml` 写入时只做了 YAML 格式校验，未跑 `_validate_config` | `do_PUT /api/config/raw?project=X` 写前做完整合并校验 | ✅ `9c73903` |
| B-016 | `config.yaml` 里 `deepseek-v4-flash` 可能是无效模型名（AGENTS §8.4） | 确认实际可用模型名，更新 config 或加备注 | 🆕 |
| B-024 | `cut.py:9` `parse_time_range` 不校验 end > start，AI 生成反向区间时 ffmpeg 静默出坏文件 | 解析后加 `if end <= start: raise ValueError(...)` | ✅ `fix/B-024-parse-time-range-validate` |
| B-025 | `tasks/cut.py:80-82` 找不到视频时的报错信息里 source 标签取反 | 修复三目运算 | ✅ `fix/B-025-cut-source-label` |
| B-026 | `tasks/plan.py:31` `int(raw_idx)` 无保护，文件名前缀非数字时抛未捕获 ValueError | 加 `try/except` 守卫跳过 | ✅ `fix/B-026-plan-int-raw-idx` |
| B-027 | `prompts.py:38-70` `PLAN_PROMPT` 用 `str.format()` 拼接含 `{...}` 的 JSON | ⚠️ 经测试 `str.format()` 不会处理替换值中的花括号，非真实 crash | ❌ 不可复现 |
| B-028 | `progress.py:42` `.with_suffix(".progress.tmp")` 生成 `.progress.progress.tmp` | 改用 `parent/name + ".tmp"` | ✅ `fix/B-028-progress-tmp-name` |
| B-029 | `log.py:101-146` `_initialized` 无锁；`sys.stdout/stderr` 不可恢复 | 加锁 + 保存原始 stream + `teardown_logging()` | ✅ `fix/B-029-log-init-lock` |
| B-030 | `pyproject.toml:3` `build-backend` 私有 API | 改用 `setuptools.build_meta:__legacy__` | ✅ `fix/B-030-pyproject-backend` |
| B-031 | `server.py:107-109` `_config_cache` 多线程无锁 | 加 `_config_cache_lock` | ✅ `fix/B-031-config-cache-lock` |
| B-038 | `server.py:393-395` Phase 1c 重构遗漏 `config_path` 类属性暴露 | 添加 `Handler.config_path = config_path` | ✅ `fix/B-031-config-path-exposure` |
| B-054 | `routes/run.py` `_run_thread` check-and-set 未受锁保护，`handle_post_run_start` / `handle_post_rerun` 可并发启动两条流水线 | `handler.__class__._run_lock` 包裹读写 | ✅ `dc01300` |
| B-055 | `server.py` `_config_cache.pop` 未加锁，并发 PUT config 时数据竞争导致缓存不一致 | 用 `_config_cache_lock` 包裹 `.pop()` | ✅ `93eb4f1` |
| B-056 | `analyze.py:_resolve_original` 只识别 `.mp4`/`.mov`/`.mkv`/`.mts`/`.m2ts`，漏 `.m4v`/`.webm` | 补全扩展名列表 | ✅ `8608d14` |
| B-057 | `server.py` 视频响应固定 `Content-Type: video/mp4`，`.mov`/`.webm` 等扩展名返回错误 MIME | 按实际文件扩展名选择 Content-Type | ✅ `18f7358` |
| B-063 | `routes/videos.py` `segment_matches` 字段前端用到但后端从未返回 | 返回 `segment_matches` 数组 | ✅ `7f05ee4` |
| B-064 | `analyze.py` `trip_context.md` 路径硬编码为包目录，多项目场景下定位错误 | 项目级优先查找 + 读缓存 | ✅ `fe57a7f` |
| B-065 | `routes/config.py`+`routes/projects.py` 8 处 `hasattr(handler.server,...)` 防御代码 | 统一在 `make_handler` 绑定后直接访问 | ✅ `34c0d3b` |
| B-066 | `server.py` `_config_cache` 无上限，长期运行内存泄漏 | LRU cap 20 条，超限淘汰最旧条目 | ✅ `e21373e` |

### P2 — 中期

| ID | 问题 | 修复思路 | 状态 |
| --- | --- | --- | --- |
| B-005 | Linux 下 `sorted(Path.iterdir())` 顺序不保证（glob 也不保证顺序） | 显式 `sorted()` 后再匹配 | ✅ `a276225` |
| B-008 | 函数隐式修改入参（如 `analyze_video` 等修改传入的 dict 字段） | 入参 `deepcopy()` 避免副作用 | |
| B-017 | `_find_texts_dirs` 匹配 `texts*` 太宽 — `texts_backup` 也会匹配 | 用更精确的 glob 或加排除规则 | ✅ `a276225` |
| B-018 | `_config_cache` 只增不减（仅在 PUT config 时 pop） | 项目列表刷新时清理失效缓存 | ✅ `a276225` |
| B-032 | `tasks/label.py:29-31` glob 时 idx 可能是整数 1 而非 `"001"`，导致文件匹配失败跳过处理 | `format_index(int(idx), config.naming.index_width)` 统一格式化后再 glob | ✅ |
| B-033 | `tasks/analyze.py:96` 批量 AI 分析失败直接中断整个批次；`run_refine_texts` 有 try/except/continue 容错而此处没有，行为不一致 | 给 `analyze_video()` 调用加 `try/except` + `continue`，记录失败继续下一个 | ✅ |
| B-034 | `routes/run.py` rerun 进度文件路径从 `cfg.paths.output_dir` 取，但 `GET /api/run/status` 从 `_project_output_dir()` 取，两个 output_dir 可能不一致导致前端轮询读不到进度 | 统一用 `proj_out`（来自 `_project_output_dir`） | ✅ |
| B-035 | `sidebar.js:448` `pollRerunStatus` 在 `idle/running` 状态提前 return 无超时兜底，任务失败时进度 overlay 永久卡死 | 加 polling 超时（120s）+ 10s idle 检测 + `_rerunPollError()` | ✅ |
| B-036 | `compress.py:33-34` 目标码率 `8 * 1024 * 1024 * target_size_mb / duration * 0.92` 未扣音频流，有音频时输出文件超过 `target_size_mb` | `target_bits` 先扣 128kbps 音频估计值 | ✅ |
| B-037 | `utils.py:139-140` `get_duration_sec` 不处理 ffprobe 输出 `"N/A"`，某些视频格式下 ValueError 无上下文 | 加 `try/except`，报错时附上文件路径 | ✅ |
| B-039 | `openai_compat.py:28` `httpx.Client` 在 `__init__` 创建后无 `close()`，长服务连接泄漏 | 添加 `close()` 方法 | ✅ |
| B-040 | `config.py:119` `_path()` 值为空时静默返回 `.`，忘记配置路径时对当前目录执行读写 | 值为空时 raise `ValueError` | ✅ |
| B-041 | `file_service.py:46` `_save_atomic` 的 `.tmp` 文件名固定，多线程下两请求同时写同一文件互相覆盖 | 加 `os.urandom(4).hex()` 随机后缀 | ✅ |
| B-058 | `file_service.py:_save_atomic` 跳过已有 `.bak` 不覆盖，旧 `.bak` 与最新内容不符，多次保存后 `.bak` 反映的是最早版本 | 改为每次保存都覆盖 `.bak` | ✅ `7868a95` |
| B-067 | `tasks/analyze.py:43` lazy `import re` 在热路径中 | 移到文件顶部 | ✅ `51f50d7` |
| B-068 | `split.py` `-c copy` 按时间切割，非关键帧处片段开头有黑帧，AI 可能误判 | 文档说明；或提供 `--reencode-split` 选项 | 🆕 |
| B-069 | `progress.py` tmp 文件名固定，多进程下可能冲突 | 改用 `os.urandom(4).hex()` 随机后缀 | ✅ `ea2e79c` |
| B-070 | `pipeline.py` 未知 step 名导致 `NoneType` 调用崩溃 | 循环前验证 step 名并提前 `raise ValueError` | ✅ `34846df` |
| B-071 | `server.py` Range 请求 `length=0`（`start=size-1` 时）未保护 | 加 `length <= 0` 边界检查 | ✅ `e21373e` |

### P3 — 长期

| ID | 问题 | 修复思路 | 状态 |
| --- | --- | --- | --- |
| B-042 | `gemini.py:41` `_wait_for_file` 无超时，文件处理卡住时永久阻塞 | 加 `timeout` 参数与 `time.monotonic()` 超时检查 | ✅ `a276225` |
| B-043 | `.githooks/pre-commit:21` `git add` 会误 stage 用户未打算提交的工作区修改 | 只 stage ruff 格式化的文件：`$RUFF format . && git diff --name-only --diff-filter=M` 前检查是否是 ruff 改的 | 🆕 |
| B-044 | `_helpers.py:51` `_eta_line` `completed=0` 时固定显示 `1/total`，实际可能是第 3、4 条 | 用 `i` 替换硬编码的 `1` | ✅ `a276225` |
| B-045 | `sidebar.js:177` 视频列表每次渲染都在 `document` 上堆积 `{ once: true }` click 监听器，关闭 dropdown 逻辑失效 | 改用事件委托 + 持久 handler，或渲染前 `removeEventListener` | ✅ `a276225` |
| B-059 | `_parse_providers` 未读取 `requests_per_minute` 与 `retry_attempts` 从 YAML | `cfg.get("requests_per_minute", 0)` + `retry_attempts` 默认值统一为 2 | ✅ `a276225` |
| B-060 | 原视频视图下 split 段 index 丢失 — 每个原文件只取 `comp[0]`，plan 引用 `002`/`003` 时找不到对应条目报 404 | 遍历 `comp` 所有匹配，每个 split 段创建独立 video entry | ✅ `c59880d` |
| B-072 | `tasks/compress.py` 损坏的 `.mp4` 会被 `skip_existing` 永久跳过不重试 | 加文件完整性校验或 fallback 重试 | 🆕 |
| B-073 | `routes/videos.py` `_parse_segment_info` 只识别 `001_GL010683_seg01` 格式 | 放宽命名格式假设，支持用户自定义命名 | 🆕 |
| B-074 | `analyze.py:_wrap_with_context` 每次 AI 调用都读 `trip_context.md` 磁盘 | 模块级 `_trip_context_cache` 缓存 | ✅ `fe57a7f` |
| B-075 | `ui/server.py` Range 请求不支持 suffix `bytes=-N` | 空 start + 非空 end → suffix 计算 | ✅ `d2591a9` |
| B-076 | `utils/discover_ffmpeg_bin` 硬编码 `G:/ffmpeg` | 移除，改为 `FFMPEG_HOME` 环境变量 | ✅ `74c34f5` |
| B-077 | `tasks/analyze.py` `_resolve_original` 无 `_` stem 时 ValueError | 前置 `if "_" not in stem:` 检查 | ✅ `e6e7666` |
| B-078 | `main.py` 不传 `project_dir` 给 `load_config`，project.yaml 被忽略 | 从 `-i` 目录或 cwd 推断 `project_dir` | ✅ `60d765f` |
| B-079 | `log.py` `_TeeWriter.__getattr__` 透传 `close`/`writelines`/`truncate` | 拦截并 raise AttributeError | ✅ `947a320` |
| B-080 | `openai_compat.py` 硬编码 `attempts=3` 忽略配置的 `retry_attempts` | 从 `cfg.retry_attempts` 读取 + `+1` 转换 | ✅ `ef2311d` |
| B-081 | `gemini.py` `retry_attempts` 与 openai_compat 语义不一致（缺 `+1`） | 对齐为 `max(1, cfg.retry_attempts + 1)` | ✅ `ef68308` |
| B-082 | `ai/factory.py` provider 缓存线程不安全 + 无测试清理机制 | 加锁 + `_clear_provider_cache()` + autouse fixture | ✅ `ef68308` |
| B-083 | `ui/routes/run.py` `obj.get("index")` 未消毒用作 glob 模式 | `re.sub(r"[^a-zA-Z0-9_-]", "")` 过滤 | ✅ `bebf21f` |
| B-084 | `ui/static/src/editor.js` `save()` 内部的数据引用未捕获 | 捕获 `planData/textsData/voiceoverData/configRaw` | ✅ `bebf21f` |
| B-085 | `ui/static/src/editor.js` 转录编辑 onblur 从 `state.currentVideo` 读而非双击时捕获 | `origV` 在 dblclick 时捕获 | ✅ `fe511be` |

## ~~测试覆盖盲区~~ ✅ 全部修复（163 新测试，2026-06-13）

所有 B-046~B-052 已被 163 个新增测试覆盖：

| ID | 优先级 | 原问题 | 修复 |
| --- | --- | --- | --- |
| B-046 | 高 | `with_retry` 无测试 | `test_utils.py::TestWithRetry`（5 测试） |
| B-047 | 高 | `cut_one` 无测试 | `test_cut.py::TestCutOne`（3 测试） |
| B-048 | 高 | `_TeeWriter` / `setup_logging` 无测试 | `test_log.py::TestTeeWriter` + `TestSetupLogging`（8 测试） |
| B-049 | 中 | `ProgressTracker.log()` 无测试 | `test_progress.py::test_log_appends` / `test_log_truncates_at_100` |
| B-050 | 中 | `resolve_binary` 无测试 | `test_utils.py::TestResolveBinary`（3 测试） |
| B-051 | 中 | ETA 测试依赖 sleep | 已改用 `mock.patch("time.monotonic")` 注入时间 |
| B-052 | 中 | ETA 断言未验证 None | 已改为 `assert data.get("eta_sec") is None` |
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
| `5029ba1` | feat(ui): play/pause toggle for preview, stop no longer resets to segment 0 |
| `e4818af` | fix(ui): preview bar blocks start preview when inactive |
| `0d322c2` | fix(ui): two-row preview bar, buttons work without clicking segment first, fix MouseEvent leak |
| `67d8b0d` | feat(ui): preview bar blocks show seg number + tooltip with title and time window |
| `de03cc2` | fix(ui): plan segment click integrates with preview system |
| `298a729` | fix(ui): correct $() calls - use IDs without # prefix |
| `d410c4e` | fix(compress): fix closure late-binding trap in progress callback |
| `129de90` | feat(ai): add structured validation for AI responses (P2-1) |
| `eb93573` | fix(analyze): clean up stale existing files on source_file mismatch (P2-6) |
| `097a6ff` | fix(split): clean up partial segments + atomic manifest (P2-2) |
| `123c84f` | fix(tasks): use atomic writes for scripts/refine output (P0-3) |
| `3ce9ef3` | fix(prompts): TRANSCRIPT_CONTEXT 英文→中文 (Q-6) |
| `cdcc873` | fix(ai): include file mtime in trip_context_cache key (P2-3) |
| `6d23de3` | fix(transcribe): use find_videos for recursive scanning (P2-5) |
| `78a0b69` | fix(compress): raise MIN_VALID_SIZE 256→50KB (P2-7) |
| `3660fea` | fix(ai): add max_tokens + temperature to OpenAI API (P1-2) |
| `a29a53c` | fix(plan): record ProcessingState after generating plan (P0-5) |
| `bebf21f` | fix(save): capture data refs at entry; sanitize index_prefix in rerun |
| `ef68308` | fix(review): align Gemini retry_attempts, thread-safe provider cache, test isolation |
| `ef2311d` | fix(ai): use configurable retry_attempts |
| `947a320` | fix(log): block destructive calls on _TeeWriter |
| `60d765f` | fix(cli): pass project_dir to load_config |
| `9288216` | fix(utils): add stdout=DEVNULL to run_ffmpeg Popen |
| `e6e7666` | fix(tasks): handle stem without underscore |
| `74c34f5` | fix(utils): remove hardcoded G:/ffmpeg |
| `b072240` | fix(security): add _is_safe_basename for cut day_label |
| `d2591a9` | fix(ui): handle suffix range bytes=-N |
| `08d815c` | fix(ui): clean up portal close listener |
| `1406e0e` | fix(ui): guard startRun with btn.disabled check |
| `8d3b2f8` | fix(ui): capture state at save() entry |
| `fe511be` | fix(ui): capture video ref at dblclick in transcript edit |
| `71659aa` | fix(ai): cache provider instances |
| `18ccee4` | fix(config): filter unknown YAML fields |
| `dba1cd9` | fix(ai): fail fast on non-retryable 4xx |
| `bce09ce` | fix(ui): replace addEventListener with onloadedmetadata |
| `89614a4` | fix(ui): delegate switchToOriginalThenCompress to setSource |
| `41abe5b` | fix(security): add _is_safe_basename guard to rerun |
| `1b53499` | fix(transcribe): resolve rerun 404, CUDA fallback, UI transcript display |
| `d0d0847` | fix(compress): fallback skip when split segments exist but source is original |
| `6a56eaf` | fix: batch fix 19 review issues from project-wide code audit |
| `fe1a078` | fix(compress): filter partial files (<256B) from existing_map |
| `1c5d681` | fix(cli): lazy imports prevent google-genai loading on whisper install |
| `8412e03` | fix(config): hf_endpoint defaults to empty, only overrides when configured |
| `31abfac` | feat(processing-state): per-file pipeline state matrix with UI table |
| `eff8fce` | feat(ui): per-file compress log in run tab panel |
| `417aa0a` | fix(ui): keep btn enabled when stale progress from interrupted run |
| `c600840` | fix(ui): pollRunStatus shows progress when s.status==='running' even without live thread |
| `11ea035` | fix(compress): skip_existing now matches existing files by stem instead of by path |
| `306f349` | feat(compress): real-time stderr progress with progress_callback for tracker |
| `1d1b46a` | fix(whisper): replace torch with ctranslate2 for CUDA detection |
| `812b520` | fix(whisper): lazy import torch in whisper_cli |
| `c6e01ec` | feat(whisper): reorder pipeline, per-video rerun, plan toggle, UI error handling |
| `34846df` | fix(pipeline): validate step names before execution |
| `ea2e79c` | fix(progress): random suffix for tmp file to avoid name conflicts |
| `34c0d3b` | refactor(ui): remove hasattr(handler.server) patterns, use direct attr access |
| `fe57a7f` | fix(analyze): use project-level trip_context.md with read cache |
| `7f05ee4` | feat(ui): return segment_matches array for multi-segment original videos |
| `51f50d7` | fix(analyze): replace *.mp4 glob with VIDEO_EXTS filtering, move import re to top |
| `e21373e` | fix(config): clear _config_cache on global config write and cap cache at 20 entries |
| `fad1cc8` | feat: add .lrv (GoPro proxy) video format support |
| `cb4d8e9` | fix(ui): delegate browse-btn click handler to cover dynamically created buttons |
| `2cc3451` | fix(cut): resolve original source path and apply segment offset for split videos |
| `86a281d` | fix(ui): add offset_sec to timeline click seek in texts tab |
| `c78622f` | fix(ui): compute segment offset_sec for original view |
| `3fb8263` | fix(ui): update plan preview counter and unique video identity for split segments |
| `e6e068c` | feat(ui): show AI analysis title below filename in sidebar video list |
| `e72ba10` | fix(ui): create per-segment entries in original video view for plan segment playback |
| `c59880d` | feat(analyze): add progress_callback for per-file upload/wait/AI/disk granularity |
| `6c2ab33` | chore: add pre-commit hook to auto-format staged .py files with ruff |
| `4d146d0` | style: ruff format vlog_tool/ui/services/file_service.py and project_service.py |
| `2f1d56c` | docs: add config hot-reload audit spec (R-015) and update ROADMAP |
| `e3f87a1` | feat(config): add migrate-config subcommand to inject provider defaults |
| `a276225` | fix: batch P2/P3 bug fixes (B-005/B-017/B-018/B-042/B-044/B-045/B-059) and config injection |
| `93eb4f1` | fix(ui): wrap _config_cache.pop with _config_cache_lock |
| `dc01300` | fix(run): serialize _run_thread check-and-set under _run_lock |
| `c283bb9` | fix(ui): hoist statusEl/fill/logsEl before early return |
| `8608d14` | fix(analyze): add .m4v and .webm to _resolve_original |
| `18f7358` | fix(ui): serve correct MIME type per video extension |
| `7868a95` | fix(ui): overwrite stale .bak in _save_atomic instead of skip |
| `3b69ff0` | fix(ui): prevent duplicate project in _list_projects |
| `e404042` | docs: add UI screenshots to README preview |
| `4aa5015` | ci: add --cov-branch, README coverage badge + 343 test table |
| `51ac8fc` | fix(tests): cross-platform CI failures (MTS case, PermissionError, thread leak) |
| `68ec476` | docs: UT-progress v2 with run_compress_all + run_analyze_all (163 new, 343 total) |
| `284ead0` | test(tasks): 6 tests for run_analyze_all duration gate + skip existing |
| `ffe0e58` | test(tasks): 3 tests for run_compress_all orchestration |
| `40431c8` | test(routes): 18 tests for run pipeline + project CRUD handlers |
| `3df0705` | test(compress): 6 tests — compress_video bitrate/flags/duration |
| `c62b507` | test(split): 7 tests — split_video segment computation |
| `a11aecd` | test(analyze): 9 tests — _wrap_with_context, plan_daily_vlog filtering |
| `6dafde9` | test(routes): 30 tests for videos/plan/config route handlers |
| `5a54a2b` | test(project_service): 22 tests — output dir, registry, step detection |
| `f9edede` | test(tasks): tests for _helpers.py + _resolve_original |
| `7e7e138` | test(file_service): 60 tests — basename/segment/atomic/config coercion |
| `c197496` | test(ai): 12 tests — factory dispatch + provider instantiation |
| `2f3c86c` | feat(ui): segment group tree in sidebar (方案B frontend) |
| `0ab6960` | feat(ui): group_key/segment_label/groups in /api/videos (方案B backend) |
| `539b587` | feat(ui): _segNN matching for compressed-original lookup (方案A) |
| `fe2134a` | feat(ai): retry Gemini ClientError 429 with should_retry callback |
| `9d69a44` | feat(split): video splitting + long-video duration gate |
| `31c972d` | fix: enable compress step in pipeline runner |
| `464c3d4`~`ba02b86` | Bug fix spree: B-021~B-041 (19 bugs: cut -to→-t, empty dir misdetect, atomic project.json, int guard, detect-steps, temp name, config cache lock, ffprobe N/A, audio bitrate budget, rerun timeout/path, save_atomic race, B-040 path empty, B-039 provider close) |
| `75b2ffd` | feat(plan): add preview playback + speed control (R-011) |
| `1912012` | refactor(ui): improve plan naming, move day selector to plan tab |
| `250a35c` | style(lint): fix all ruff CI lint errors |
| `c474830` | test: with_retry, cut_one, TeeWriter, ProgressTracker.log (B-046~B-052) |
| `b0da41a` | refactor: split app.js into ES modules (Phase 1d) |
| `0918da0` | refactor: split server.py into routes/ and services/ (Phase 1c) |
| `cac4d67` | refactor: split pipeline.py into tasks/ package (Phase 1b) |
| `5e8d376` | refactor: extract global constants to _constants.py (Phase 1a) |
| `b6b84df`..`66613cc` | CI + 118 original tests (config/utils/cut/log/progress) |
| `a8daa63` | feat(ui): pipeline step selection with checkboxes (R-005f) |
| `29bcb35` | feat(ui): pipeline runner with progress tracking (R-005) |
| `a3d2fe0` | feat(ui): multi-project switching with create (R-007) |
| `9c73903` | fix: P0 bugs B-012/B-013/B-015 + lock dependency versions |
| `a93b5f5` | R-004 UI 配置编辑（后端 raw config API / 递归嵌套表单 / 校验 + .bak 保存 / 文档） |
| `6706dc3`..`2ad23f5` | R-002 CLI + UI 裁剪（cut.py + POST /api/cut + cut tab + manifest.md） |
| `0d52cf6`..`439911c` | 本地 Web UI（backend / CLI / frontend / docs / plan-seek fix） |
| `88679ee`..`ec83f48` | R-001 UI 源切换（后端双 source / 顶部 toggle + match 角标） |
| `a648e60`..`778c44a` | R-006 sidebar 分层（HTML+CSS / JS state machine / README 布局图） |
| `d6d62ef` | feat(config): per-project configuration via project.yaml |
| `a9996a9` | fix(ai): clean up Gemini File API uploads + retry (B-001, B-002) |
| `25128d1` | feat(ai): retry transient API failures with exponential backoff |
