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
- [ ] R-004a：后端 `GET /api/config/raw` 返回 config 原始 dict；`PUT /api/config/raw` 校验并写回（带 .bak 备份）
- [ ] R-004b：UI 加「设置」tab；渲染完整 config 为嵌套 form（dict / list / scalar）
- [ ] R-004c：UI 表单编辑 + 保存（弹确认 → PUT → 提示重启 + 校验失败红字）
- [ ] R-004d：文档：`vlog_tool/ui/README.md` 加「设置」tab 用法

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
- [ ] R-005a：`vlog_tool/progress.py` ProgressTracker：写 `output/.progress.json`（phase / current / total / message / started_at / eta / status）
- [ ] R-005b：接入 `pipeline.run_analyze_all`：compress / analyze / voiceover / plan 关键节点调 `tracker.update`
- [ ] R-005c：后端 `POST /api/run/start`（daemon 线程 + lock 防并发）；`GET /api/run/status` 读 `.progress.json`
- [ ] R-005d：UI 头部「运行」按钮 + 进度面板（轮询 2s，渲染 phase / [i/N] / ETA / status）
- [ ] R-005e：文档：`vlog_tool/ui/README.md` 加运行面板

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
- [ ] R-006a：`vlog_tool/ui/static/index.html` + `style.css`：sidebar 两段结构 + 灰显样式
- [ ] R-006b：`vlog_tool/ui/static/app.js`：state.currentEntity + selectPlan + 右栏内容分发；plan 内容从 tab 拆出来作为独立渲染分支
- [ ] R-006c：`vlog_tool/ui/README.md`：界面布局图更新 + 项目级 section 说明


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
- [ ] R-002a：`vlog_tool/cut.py`：`cut_one(video, start, end, out, *, reencode=False)` 包装 ffmpeg
- [ ] R-002b：`vlog_tool/cut.py`：`parse_time_range("00:00-00:20")` 复用 utils 已有逻辑
- [ ] R-002c：`pipeline.py`：`run_cut_all(config, day, output_dir, reencode=False)` + 进度
- [ ] R-002d：`main.py`：`cut` 子命令（`--day`, `--output`, `--reencode`）
- [ ] R-002e：配套 texts JSON 复制到 `cuts/<day>/`（重命名 `001_xxx_seg_03.json`）
- [ ] R-002f：进度走 `timed()` + `[i/N]` + ETA（与现有 pipeline 一致）
- [ ] R-002g：生成 `manifest.md`（markdown 表格：# / 视频 / 时间 / 输出文件 / 标题）
- [ ] R-002h：文档：`README.md` 加 `cut` 子命令

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
- [ ] R-003a：审计现有子命令的 `-i` 单文件支持（`compress` / `analyze` / `scripts` / `plan` / `refine`）
- [ ] R-003b：缺啥补啥（预期缺 `voiceover` 的 `-i` 单 JSON 支持）
- [ ] R-003c：`refine --context "..."` 参数：临时追加到 prompt，写在 `ai.context` 之后
- [ ] R-003d：UI 视频列表每项加 dropdown「重跑 texts / voiceover / 全部 / 标记 refine」
- [ ] R-003e：UI refine tab 加临时 context textarea
- [ ] R-003f：后端 `POST /api/rerun` 接受 `{video: <basename>, task: 'texts'|'voiceover'|'all'}`
- [ ] R-003g：`pipeline.py`：`run_rerun_single(config, video_file, task_name)`

## 暂存 / WIP

- `templates/trip_context_2.md`（蓝色旗子场景的小补丁）— 写好但未启用，启用时只需在
  `config.yaml` 把 `ai.context_file` 切到它

## 已完成（最近，按时间倒序）

| Commit | 简述 |
| --- | --- |
| `0d52cf6`..`439911c` | 本地 Web UI（拆 6 commit：backend / CLI / frontend / docs / plan-seek fix / AGENTS 同步） |
| `88679ee` `f1d09ac` `ec83f48` | R-001 UI 源切换（后端双 source / 顶部 toggle + match 角标 / README 文档） |
| `a2597f0` | 删 plan tab 跳转 bug |
| `25128d1` | AI 调用加重试与退避 |
| `835b7e9` | 配置加载时校验 proxy / tasks |
| `b503c9c` | 日志助手 `format_size` / `format_duration` / `timed` |
| `3d39b6a` | 未捕获异常整成一条 ERROR 日志 |
| `9d5b393` | ffmpeg / AI 详细日志 + ETA 进度 |
| `19e9b8e` | 删孤立的 `video_analysis.py` |
| `3a2ca76` | `extract_json` 从 `ai/gemini.py` 移到 `utils.py` |
| `d98b233` | AGENTS.md refresh（--fix, log helpers） |
