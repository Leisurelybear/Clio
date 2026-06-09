# AGENTS.md — AI 维护手册 & 项目记忆

> 这份文档是给**未来接手维护的 AI 助手**看的快速参考。
> 内容会随着项目演化更新；和 `README.md`（面向最终用户）分工不同。
> 用户偏好：中文对话界面，commit message 和这份文档用**英文**。

## 1. 项目一句话

一个 **AI 预处理流水线**：旅行 vlog 原始素材 → ffmpeg 压缩 → Gemini 看视频 + DeepSeek 写文案 → 剪映手工剪辑。
最终用户是单人 vlogger，先压缩丢给 AI，再在剪映里加特效/对口型。

## 2. 技术栈

- **Python 3.11+**（用了 PEP 604 的 `X | None` 和 dataclass）
- **ffmpeg / ffprobe**（视频处理；GoPro 4K 源文件 → 640p 5MB 压缩版）
- **google-genai**（Gemini 2.5 Flash 的视频 File API）
- **httpx**（DeepSeek / OpenAI 兼容调用）
- **PyYAML**（config 解析）
- 没有写测试，靠手动 `python main.py check` 和跑通一个真实素材目录验证

依赖列表在 `requirements.txt`，`setup.ps1` 一键建 venv + 装 ffmpeg + 拷 `.env`。

## 3. 目录结构

```
vlog-video-analysis/
├── main.py                    # CLI 入口，所有 subcommand 在这里注册
├── vlog_tool/
│   ├── config.py              # AppConfig dataclass + load_config
│   ├── pipeline.py            # 高层流水线函数（run_analyze_all 等）
│   ├── analyze.py             # AI 交互（analyze_video, generate_voiceover, plan_daily_vlog, refine_*）
│   ├── compress.py            # ffmpeg 包装
│   ├── prompts.py             # 所有 prompt 模板（常量）
│   ├── utils.py               # ffmpeg 路径发现、文件 IO、mask_if_looks_like_key、extract_json
│   ├── log.py                 # 日志：按小时切文件 + _TeeWriter + timed/format_size/format_duration
│   │                           #     + sys.excepthook 把未捕获异常整成一条 ERROR 日志
│   ├── ui/                    # 本地 Web UI（可视化编辑 AI 输出；stdib http.server，零新依赖）
│   │   ├── server.py            #   UIHandler（BaseHTTPRequestHandler）+ make_handler + run
│   │   ├── README.md            #   UI 使用文档
│   │   └── static/              #   前端三件套（无构建步骤）
│   │       ├── index.html
│   │       ├── app.js
│   │       └── style.css
│   └── ai/
│       ├── base.py            # TaskName 枚举、Provider Protocol
│       ├── factory.py         # 按名字查找 provider
│       ├── gemini.py          # 多模态：File API 上传 + 轮询 PROCESSING（已包 with_retry）
│       └── openai_compat.py   # OpenAI 兼容：DeepSeek / OpenAI / 通义 / Moonshot（已包 with_retry）
├── templates/
│   ├── vlog_template.md       # 口播风格模板（用户可改）
│   └── trip_context.md        # trip 背景与 AI 规范（自动注入到所有 prompt）
├── config.example.yaml        # 提交到 git 的配置模板
├── .env.example               # 提交到 git 的环境变量模板
├── config.yaml / .env         # 用户本地真实配置，gitignore
├── logs/                      # 运行日志（gitignore；按小时切：YYYY-MM-DD-HH.log）
├── setup.ps1                  # 一键环境
├── README.md / README.en.md   # 用户文档（双语）
├── ROADMAP.md                 # 需求追踪（sub-task 粒度）
└── AGENTS.md                  # 本文件
```

## 4. 关键约定

### 4.1 Commit

- **英文** message，**Conventional Commits** 风格：`type(scope): subject`
- **每个 commit 尽可能小**，覆盖一个独立的小功能/修复模块，方便后续分支开发和回滚
- **不要把多个独立功能合在一个 commit 里**
- 常见 type：`feat` / `fix` / `refactor` / `docs` / `chore`
- rebase 改历史时优先用 `git rebase -i --root`；Windows 下交互式 editor 容易卡，用 `git filter-branch --msg-filter` 走字节级 Python 脚本（见 [§8 Gotchas](#8-gotchas)）

### 4.2 工作流程

- **先规划再实现**：任何功能改动前，先在 AGENTS.md 或 ROADMAP.md 记录规划，确定方案后再写代码
- **功能模块记录**：每个新增功能模块必须在文档中记录（README.md 面向用户，AGENTS.md 面向 AI），包括用途、入口、关键约定

### 4.3 代码风格

- 不要写注释，除非解释**为什么**（WHAT 自己看得见）
- 中文 user-facing 文案（CLI 提示、错误信息、README 中文版）
- 默认 `skip_existing=True` 的策略被所有 step 共享（改 `analyze` 这一个开关就行）
- AI 返回的 JSON 用 `extract_json()` 容错（先 `json.loads`，再正则抓 `{}`）

### 4.4 配置

- 仓库提交 `config.example.yaml` 和 `.env.example`；真实 `config.yaml` 和 `.env` 在 `.gitignore` 里
- 任何含**本地路径、代理 IP、API key** 的字段都不要进 example（用占位符）
- 配置文件改动后建议同时更新 example 和 README/en

### 4.5 提示词

- 全部放在 `vlog_tool/prompts.py`，用常量
- trip 上下文通过 `_wrap_with_context()` 在所有 prompt 前面统一注入；**不要**在每个 prompt 里手写 prefix
- 输出格式必须是 JSON（不是 markdown 代码块），`extract_json()` 才能解析

### 4.6 未来重构方向

- **模块拆分**：当前 `server.py` / `app.js` 集中了 UI 层所有逻辑，后续应该拆成不同文件/目录，每个负责独立功能
- **去本地化**：移除所有代码中硬编码的本机路径、机器名、特定目录结构等，方便项目通用化/开源
- **两阶段计划已定稿**，见 `docs/superpowers/specs/2026-06-09-architecture-cleanup-and-r008-design.md`
  - Phase 1：server.py 拆 routes/ + services.py，app.js 拆 state/api/viewer，.gitignore 补漏，去本地化，修 bug
  - Phase 2：R-008 UI 单步执行（选目录 → 选文件 → 跑步骤 → 进度 → 自动刷新）

## 5. 添加新功能的标准做法

> **先在 `ROADMAP.md` 录一条需求，拆成 sub-task，再开干。** 完成时把对应 sub-task 标 `[x]`
> 并把 commit hash 写到"已完成"表里。AGENTS.md 里的 commit 列表会定期跟 ROADMAP 对齐。

### 加一个新的 AI 厂家

1. `vlog_tool/ai/newprovider.py` 实现 `TextAIProvider` 和/或 `VideoAIProvider`
2. `vlog_tool/ai/factory.py:_PROVIDER_TYPES` 注册
3. `config.example.yaml` 加 example；`main.py:check` 会自动列出
4. README（CN/EN）补一句用法

### 加一个新的 AI 任务（如"字幕翻译"）

1. `vlog_tool/ai/base.py:TaskName` 加枚举值
2. `vlog_tool/prompts.py` 加 prompt 常量
3. `vlog_tool/analyze.py` 加 `task_xxx()` 函数，复用 `_wrap_with_context()`
4. `vlog_tool/pipeline.py` 加 `run_xxx_all()`
5. `main.py` 注册 subcommand
6. 更新 READMEs

### 改 refine 阶段用的 AI

`refine_text` 默认回退到 `video_analyze`（texts 和 scripts 审阅共用这一个）
（逻辑在 `vlog_tool/config.py:_parse_tasks`）。要切到更便宜的纯文本模型，
在 `ai.tasks` 里显式加：

```yaml
ai:
  tasks:
    refine_text:
      provider: deepseek
      model: deepseek-chat
```

### refine 加定向修正模式（`--fix`）

对已知的具体错误（地名拼错、编号错了等），`refine --fix '...'` 比
让 AI 自由审阅更可靠：

- 必须配合 `-i` 指定**单个** json 文件（避免误伤）
- 切换 prompt 到「按用户意见定向修正」，AI 只改意见中提到的字段
- `_changelog` 第一条固定写"按用户意见修改了 XXX"，方便审计
- 实现：`vlog_tool/prompts.py` 的 `REFINE_TEXT_FIX_PROMPT` /
  `REFINE_SCRIPT_FIX_PROMPT`，`analyze.py` 的 `refine_text(refine_script)` 多一个 `fix` 参数

### 加一个新的 CLI subcommand

1. `main.py` 加 `p_X = sub.add_parser(...)` 和 dispatch 分支
2. 复用 `_add_io_args()` 拿到 `-i/-o`
3. 用 `config.analyze.skip_existing` 控制是否跳过（保持和其它 step 一致）
4. 更新 READMEs

## 6. 用户偏好（持久化记忆）

- **语言**：对话用中文，commit/PR/AGENTS.md 用**英文**
- **Commit 粒度**：一功能一 commit，**不要**攒
- **历史改写**：用户接受 force-push 改 commit message（rebase / filter-branch）
- **不要**在配置文件里留真实 API key / 代理 IP / 本地路径
- **不要**写测试代码（除非用户明确要求）
- 看到 `<system-reminder>` 里的工作目录、当前时间等信息时，不要在回答里复述
- **Push 之前必须显式向用户确认**。本地 commit 可以做（实现完一个功能就 commit），
  但 `git push` 永远要先停下问一句"是否 push"，等用户点头再执行。

## 7. 项目当前状态

最后更新：2026-06-10（全面 review + ROADMAP 同步）。
最近做的 commit 顺序：
1. `chore: scaffold initial Vlog editing helper project`
2. `fix(compress): escape comma in scale expression`  ← Windows ffmpeg filter 逗号转义
3. `feat(pipeline): make all steps resume-safe`  ← skip_existing 真接上
4. `docs: add English README and link from Chinese README`
5. `fix(ai): clearer error when API key is missing or misconfigured`  ← 防止 key 被回显
6. `feat(ai): support per-trip context preamble`  ← ai.context / ai.context_file
7. `feat(cli): add refine subcommand to polish existing outputs`  ← 用 trip context 修正旧输出
8. `docs: add AGENTS.md`  ← AI 维护手册
9. `feat(ai): independent provider for refine tasks`  ← refine_text 独立可配（texts/scripts 共用）
10. `feat(log): persist execution logs to per-hour files`  ← logs/YYYY-MM-DD-HH.log（gitignored）
11. `docs: expand command reference with per-subcommand sections`  ← README 命令参考细化
12. `feat(refine): add --fix mode for targeted single-file corrections`  ← 定向修正 prompt
13. `feat(log): add format_size, format_duration, and timed() helpers`  ← 日志助手函数
14. `feat(integration): detailed logs - commands, sizes, AI timing, ETA progress`  ← 接入 compress/analyze/pipeline
15. `fix(log): uncaught exceptions as one ERROR entry, not per-line noise`  ← sys.excepthook
16. `chore: remove orphan video_analysis.py`  ← 已废弃的单文件 demo
17. `refactor(utils): move extract_json out of ai/gemini.py`  ← 通用工具不应在 gemini 模块
18. `feat(config): validate proxy/tasks at load time`  ← 拼写错误提前 fail
19. `feat(ai): retry transient API failures with exponential backoff`  ← with_retry 助手，gemini 5xx + openai 429/5xx
20. `feat(ui): add stdlib HTTP server backend for visual editor`  ← vlog_tool/ui/server.py，纯 stdlib
21. `feat(ui): add 'serve' subcommand to start the UI from the CLI`  ← main.py 13 行
22. `feat(ui): add HTML/CSS/JS frontend for the visual editor`  ← 静态三件套，无构建
23. `docs(ui): document the visual editor UI`  ← vlog_tool/ui/README.md + 两份顶层 README
24. `fix(ui): plan tab sequence click now also seeks the video`  ← 解析 use_timeline 起始时间
25. `feat(ui): backend supports source=compressed|original for videos and video`  ← R-001 后端，server.py +91/-28
26. `feat(ui): add source toggle with match indicators`  ← R-001 前端，HTML/CSS/JS +63/-4
27. `docs(ui): document source toggle`  ← R-001 文档，ui/README.md +31/-1
28. `fix(ui): accept CJK punctuation (full-width colon) in basenames`  ← 沙盒正则过严，`：` U+FF1A 被拒，video 002 voiceover 404
29. `docs: add R-006 (UI sidebar project/video hierarchy) to ROADMAP`  ← R-006 ROADMAP 录入
30. `feat(ui): split sidebar into project and video sections`  ← R-006a HTML+CSS，sidebar 两段结构
31. `feat(ui): wire sidebar project/video hierarchy with entity state machine`  ← R-006b JS，state.currentEntity + selectPlan
32. `docs(ui): document sidebar project/video hierarchy`  ← R-006c README 布局图更新
33. `fix(ui): use querySelector for the plan project-item in updateEntityUI`  ← $ 是 getElementById，CSS 选择器要用 querySelector
34. `fix(ui): plan segment click plays the video without switching entity`  ← plan/video 独立：playVideoSegment 不动 entity
35. `fix(ui): source toggle in plan view does not switch entity`  ← setSource 分支：plan 时只刷新列表+清空 player，不调 selectVideo；renderActiveTab 同步刷新 plan 节点的 v.file
36. `feat(ui): add config editor (R-004)`  ← 后端 raw config API + 校验 + .bak 保存；前端递归嵌套表单渲染 + 保存提示重启
37. `feat(ui): add one-click cut from plan (R-002)`  ← cut CLI + cut API + UI cut tab
38. `fix(cut): support per-day original source and plan day selection`  ← cut 双日修复
39. `fix(ui): plan-not-found handling and segment _cut_info JSON`  ← cut 边角 case
40. `feat(ui): add project metadata with persistent source/day state`  ← project.json
41. `feat(ui): add pipeline runner with progress tracking (R-005)`  ← run tab + ProgressTracker + 后台线程
42. `feat(ui): pipeline step selection and done() param fix`  ← R-005f checkbox 选步骤 + R-005g done() 修复
43. `feat(ui): multi-project switching with create (R-007)`  ← /api/projects, /api/project/create, sidebar selector, modal, URL param switching, empty state
44. `fix(ai): clean up Gemini File API uploads and move upload out of retry`  ← B-001+B-002，上传仅一次 + finally 清理
45. `fix(ui): prevent temp file leak on interrupt in config save`  ← B-003，NamedTemporaryFile → with 语句 + 显式 unlink
46. `feat(config): per-project configuration via project.yaml`  ← deep_merge + _get_config cache + server.py 适配
47. `chore: add local state files to .gitignore`  ← projects.json + *.bak + .opencode/
48. `fix: address review findings - gemini upload cleanup scope and project config validation`  ← 上传移入 try + PUT project.yaml 校验修正
49. `fix(ui): fall back to global config when project has no project.yaml`  ← 无 project.yaml 时回退到 config.yaml 而非返回空
50. `docs(roadmap): record comprehensive code review findings`  ← B-012~B-020 + D-001~D-004 + A-001~A-005

用户当前行程：**2025 年国庆节法国巴黎 7 日自由行**（`templates/trip_context.md`）
已知 AI 误判坑：把戴高乐机场 RER 认成曼谷素万那普 → context 第 5 节已写明。

项目文档状态：
- `ROADMAP.md` 当前跟踪：R-001（✓）/ R-002（✓）/ R-003/ R-004（✓）/ R-005（✓）/ R-006（✓）/ R-007（✓）/ R-008/ R-009/ R-010 + Bug 跟踪（B-001~B-020）+ 性能优化（P-001~P-003）+ 文档维护（D-001~D-004）+ 架构改进（A-001~A-005）
- B-001/B-002/B-003 已修复；仍有多项 P0~P3 Bug 待修
- per-project 配置已实现：每个项目目录下可选 `project.yaml`，deep-merge 覆盖全局 config.yaml

## 8. Gotchas（踩过的坑）

### 8.1 ffmpeg filter 表达式里的逗号

`scale=min(640,iw):-2` 里 `,` 会被 ffmpeg 解析为 filter 链分隔符。
**必须**写成 `scale=min(640\,iw):-2`（Python 源码里 `\\,`）。
详见 `vlog_tool/compress.py:24`。

### 8.2 Windows + `git filter-branch --msg-filter`

- `cmd /c` 调用 git 时，路径里的 `\` 会被 shell 当转义符吃掉 → 统一用正斜杠
- 中国版 Windows 的 `sys.stdin.encoding` 默认 **GBK**，UTF-8 输入会被解码成 `?` → Python 过滤脚本**必须**用 `sys.stdin.buffer.read()` 按字节匹配，**不要**用 `sys.stdin.read()` 文本模式
- PowerShell 调用 bat 文件时，`%1` 之类参数里包含空格的路径会被拆分 → 在 bat 文件里用 `%~nx1` 只取文件名做判断

### 8.3 Gemini File API

- 上传后文件状态是 `PROCESSING`，必须轮询到 `ACTIVE` 才能调 generate_content
- 轮询间隔在 `ai.providers.gemini.poll_interval_sec`（默认 5 秒）
- 国内访问需要走 SOCKS5 代理；用 google-genai 的 `HttpOptions(transport=httpx.HTTPTransport(proxy=...))`

### 8.4 DeepSeek 模型名

- 标准模型：`deepseek-chat`（V3）、`deepseek-reasoner`（R1）
- 用户配置里的 `deepseek-v4-flash` 是占位/自定义名 → 实际请求 404 时改回 `deepseek-chat`

### 8.5 `api_key_env` 字段

- 这是**环境变量名**（如 `DEEPSEEK_API_KEY`），不是 key 本身
- 旧代码错误地把 key 填到 `api_key_env` 字段，错误信息会把 key 露出来
- 修复：`vlog_tool/utils.py:mask_if_looks_like_key()` 检测 `sk-` / `AIza` 等前缀并遮蔽

### 8.6 `analyze.skip_existing` 名字误导

- 字段名虽然叫 `skip_existing`，实际是**所有 step 共享的跳过开关**
- 不要新建一个 `scripts.skip_existing` —— 复用这一个

### 8.7 Gemini Files API 上传未清理

- `gemini.py` 中 `ensure_file_active` 上传视频到 File API 后，调用完成后**不会**请求删除文件
- 多次 analyze 会累积大量文件，最终耗尽配额（每分钟/每天上传次数限制）
- 修复：在 `finally` 块调用 `client.files.delete(name=file.name)` 确保清理
- 注意：`with_retry` 不应包裹上传操作（否则重试时重复上传），上传成功后只重试 `wait` 和 `generate_content`

### 8.8 临时文件残留

- 项目中多处使用 `NamedTemporaryFile(delete=False)` 后忘记 `os.unlink`
- `interrupt` / `KeyboardInterrupt` 时 .tmp 文件不会自动清理
- 排查：检查 `server.py` / `utils.py` 中的临时文件用法，优先用 `delete=True` 或 `try/finally`

### 8.9 函数副作用

- `analyze_video` / `generate_voiceover` 等函数会修改传入的 dict 字段（如添加 `_file_path` 等标记）
- 调用方如果复用了同一个 dict 会出现非预期的副作用
- 修复：在修改前对入参做 `copy.deepcopy()`

### 8.10 文件排序跨平台不一致

- `Path.iterdir()` 在 Windows 上按文件系统顺序（近似创建时间），Linux 上不保证顺序
- 这会导致 `index` 分配在不同系统上不一致
- 修复：总是用 `sorted(Path.iterdir())` 保证统一顺序

## 9. 验证流程

最小验证：
```bash
.\.venv\Scripts\python.exe main.py check    # 环境检查
```

跑通一个素材目录：
```bash
.\.venv\Scripts\python.exe main.py analyze --force    # 全跑一次
.\.venv\Scripts\python.exe main.py analyze             # 验证 skip 生效（应全跳过）
.\.venv\Scripts\python.exe main.py refine              # 验证 trip context 注入
.\.venv\Scripts\python.exe main.py serve --no-browser  # 验证 UI 起得来（再 Ctrl+C 退出）
```

## 10. 沟通模板

如果是 AI 助手接手，看到 `AGENTS.md` 后应该：

1. `git log --oneline -10` 了解最近改动
2. `git status` 看是否有未提交改动
3. 读 `config.example.yaml` 了解配置结构
4. 读 `templates/trip_context.md` 了解当前行程背景
5. 询问用户具体要做什么，不要假设

如果是新功能：**先讨论方案 → 用户确认 → 实现 → 一个 commit → push**。
**不要**自动 commit / push（除非用户明确说"帮我提交"）。
