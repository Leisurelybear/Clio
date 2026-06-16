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
- **pytest**（单元测试，CI 自动跑；核心纯函数已覆盖 128 个测试用例）

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
│   ├── transcribe.py          # Whisper ASR 转录核心
│   ├── whisper_cli.py         # whisper install/check CLI
│   ├── utils.py               # ffmpeg 路径发现、文件 IO、mask_if_looks_like_key、extract_json
│   ├── log.py                 # 日志：按小时切文件 + _TeeWriter + timed/format_size/format_duration
│   │                           #     + sys.excepthook 把未捕获异常整成一条 ERROR 日志
│   ├── tasks/                 # pipeline 步骤（拆分自 pipeline.py）
│   │   ├── transcribe.py        # Pipeline task: run_transcribe_all
│   │   └── ...
│   ├── ui/                    # 本地 Web UI（可视化编辑 AI 输出；stdib http.server，零新依赖）
│   │   ├── server.py            #   UIHandler（BaseHTTPRequestHandler）+ make_handler + run
│   │   ├── README.md            #   UI 使用文档
│   │   ├── routes/              #   路由处理
│   │   │   ├── transcripts.py   #   Transcript GET/PUT API
│   │   │   └── whisper_routes.py#   Whisper check API
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
├── requirements.txt           # 开发期宽松依赖
├── requirements-locked.txt    # 可重现构建锁定版本
├── .github/workflows/test.yml # GitHub Actions CI（pushes + PRs）
├── vlog_tool/tests/           # 单元测试（pytest，381 用例）
│   ├── conftest.py            #   共享 fixtures
│   ├── test_config.py         #   34 tests - config 加载/合并/校验
│   ├── test_utils.py          #   34 tests - extract_json/mask_key/sanitize/find_videos
│   ├── test_cut.py            #   25 tests - 时间解析/文件名生成
│   ├── test_log.py            #   13 tests - TeeWriter/size&duration 格式化
│   ├── test_progress.py       #   12 tests - ProgressTracker read/write/init
│   ├── test_transcribe.py     #   15 tests - transcribe enabled/disabled/deps
│   └── test_routes_transcripts.py #  7 tests - transcript/whisper API routes
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
  - Phase 1：server.py 拆 routes/ + services.py，app.js 拆 state/api/viewer，.gitignore 补漏，去本地化，修 bug — **已完成**
  - Phase 2：R-008 UI 单步执行（选目录 → 选文件 → 跑步骤 → 进度 → 自动刷新）
- **FFMPEG_HOME** 环境变量取代硬编码路径；`discover_ffmpeg_bin` 搜索链：`shutil.which` → WinGet Packages → `FFMPEG_HOME`
- **Provider 缓存**：`ai/factory.py` `_provider_cache` 按名缓存，`_provider_cache_lock` 线程安全，`_clear_provider_cache()` 测试隔离
- **Config 未知字段**：`_filter_dc()` 过滤 YAML 未知字段再送入 dataclass 构造器，静默忽略拼写错误

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

最后更新：2026-06-16（Whisper 全功能 + 385 测试稳定 + 6+12+25 项代码审查修复）。已上线：
- GitHub Actions CI（Ubuntu，Python 3.11/3.12）
- 385 个 pytest 用例：config(34) / utils(34) / cut(25) / log(13) / progress(12) / file_service(60) / project_service(22) / routes(48) / tasks(12) / split(7) / compress(6) / analyze(15) / ai(12) / helpers(20) / file_service_routes(35) / transcribe(15) / routes_transcripts(7) + 更多
- 依赖版本锁定 `requirements-locked.txt`
- Whisper ASR 独立 `requirements-whisper.txt`（faster-whisper，不污染主依赖）
最近做的 commit 顺序：
1. `chore: scaffold initial Vlog editing helper project`
2. `fix(compress): escape comma in scale expression`  ← Windows ffmpeg filter 逗号转义
...（#3~#98 同上）...
98. `bcfbe04` `feat(ui): add transcripts tab, sidebar badge, and run step`  ← Task 8
99. `c6e01ec` `feat(whisper): reorder pipeline, add per-video transcribe rerun, plan toggle, and UI error handling`  ← 综合增强
100. `1d1b46a` `fix(whisper): replace torch with ctranslate2 for CUDA detection (no torch dependency)`  ← 去掉 torch
101. `306f349` `feat(compress): real-time stderr progress with progress_callback for tracker`  ← 实进度
102. `11ea035` `fix(compress): skip_existing now matches existing files by stem instead of by path`  ← stem 匹配
103. `c600840` `fix(ui): pollRunStatus shows progress when s.status==='running' even without live thread`  ← 进度面板
104. `417aa0a` `fix(ui): keep btn enabled when stale progress from interrupted run`  ← 按钮状态
105. `eff8fce` `feat(ui): per-file compress log in run tab panel`  ← 压缩日志
106. `31abfac` `feat(processing-state): per-file pipeline state matrix with UI table`  ← 状态矩阵
107. `8412e03` `fix(config): hf_endpoint defaults to empty, only overrides when configured`  ← 配置修复
108. `1c5d681` `fix(cli): lazy imports prevent google-genai loading on whisper install`  ← 惰性导入
109. `fe1a078` `fix(compress): filter partial files (<256B) from existing_map`  ← 过滤残损文件
110. `6a56eaf` `fix: batch fix 19 review issues from project-wide code audit`  ← 批量修复
111. `d0d0847` `fix(compress): fallback skip when split segments exist but source is original`  ← compress 分支
112. `1b53499` `fix(transcribe): resolve rerun 404, CUDA fallback, UI transcript display and seek`  ← 综合修复
113. `41abe5b` `fix(security): add _is_safe_basename guard to POST /api/rerun`  ← C1
114. `89614a4` `fix(ui): delegate switchToOriginalThenCompress to setSource`  ← C2
115. `bce09ce` `fix(ui): replace addEventListener with onloadedmetadata`  ← C3
116. `dba1cd9` `fix(ai): fail fast on non-retryable 4xx errors in OpenAI compat`  ← C4
117. `18ccee4` `fix(config): filter unknown YAML fields from dataclass constructors`  ← C5
118. `71659aa` `fix(ai): cache provider instances to prevent HTTP connection leak`  ← C6
119. `fe511be` `fix(ui): capture video ref at dblclick in transcript edit`  ← I1
120. `8d3b2f8` `fix(ui): capture state at save() entry`  ← I2
121. `1406e0e` `fix(ui): guard startRun with btn.disabled check`  ← I3
122. `08d815c` `fix(ui): clean up portal close listener`  ← I4
123. `d2591a9` `fix(ui): handle suffix range bytes=-N`  ← I5
124. `b072240` `fix(security): add _is_safe_basename for cut day_label`  ← I6
125. `74c34f5` `fix(utils): remove hardcoded G:/ffmpeg`  ← I7
126. `e6e7666` `fix(tasks): handle stem without underscore`  ← I8
127. `9288216` `fix(utils): add stdout=DEVNULL to Popen`  ← I9
128. `60d765f` `fix(cli): pass project_dir to load_config`  ← I10
129. `947a320` `fix(log): block destructive calls on _TeeWriter`  ← I11
130. `ef2311d` `fix(ai): use configurable retry_attempts`  ← I12
131. `ef68308` `fix(review): align Gemini retry_attempts, thread-safe provider cache, test isolation`  ← 审查反馈
132. `bebf21f` `fix(save): capture data refs at entry; sanitize index_prefix in rerun`  ← 审查反馈

用户当前行程：**2025 年国庆节法国巴黎 7 日自由行**（`templates/trip_context.md`）
已知 AI 误判坑：把戴高乐机场 RER 认成曼谷素万那普 → context 第 5 节已写明。

项目文档状态：
- 2026-06-16 全面代码审查（5 路平行 subagent）：发现 **6 Critical + 12 Important + 36 Minor**，已修复 6+12+5，剩余 31 Minor 待处理
- `ROADMAP.md` 当前跟踪：R-001（✓）/ R-002（✓）/ R-003/ R-004（✓）/ R-005（✓）/ R-006（✓）/ R-007（✓）/ R-008/ R-009/ R-010/ R-011（✓）/ R-012/ R-013（✓）/ R-014/ R-015（a[✓] d[✓]）+ Bug 跟踪（B-001~B-085）+ 性能优化（P-001~P-003）+ 文档维护（D-001~D-004）+ 架构改进（A-001~A-006）+ 代码审查 P0~P3（14 项修了 12 项）
- Whisper ASR 已完全接入：独立 CLI（transcribe / whisper install / whisper check）+ pipeline 步骤 + UI 转录 tab + delete/edit/seek + 10% 进度 + CUDA 回退 CPU + 每视频 rerun
- per-project 配置已实现：每个项目目录下可选 `project.yaml`，deep-merge 覆盖全局 config.yaml
- 视频分段压缩已实现（split.py + compress Phase 1/2），默认 15 分钟分割阈值
- UI compressed view 已支持 `_segNN` 分组树；原视频视图下 split 段独立条目 + offset_sec 换算
- AI 分析进度已细化：`progress_callback` 贯穿分析全流程
- Provider 缓存：factory 按名缓存，线程安全，测试隔离自动清理
- 安全修复：rerun/cut 路径遍历防御（`_is_safe_basename`），4xx 非重试错误立即失败，`index_prefix` 消毒
- 配置修复：YAML 未知字段静默忽略，`project.yaml` CLI 生效，`FFMPEG_HOME` 环境变量支持

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
- 三方 API 网关可能支持自定义名如 `deepseek-v4-flash`，按实际可用名填写即可
- 如遇 `404` 或 `model not found`，先回退到官网标准模型名验证

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

### 8.11 Pre-commit hook

- 项目在 `.githooks/pre-commit` 提供了一个 Python 脚本，自动对暂存的 `.py` 文件执行 `ruff format` 后重新 stage
- `setup.ps1` 会自动设置 `git config core.hooksPath .githooks`
- 手动配置：`git config core.hooksPath .githooks`
- hook 依赖 `.venv` 中的 ruff，找不到时静默跳过（不阻塞 commit）

### 8.12 `_filter_dc()` 与 dataclass 构造

- YAML 中拼写错误的字段名（如 `whisper.modle_size`）会导致 `TypeError: unexpected keyword argument`
- 修复：所有 `**raw` 解包前调用 `_filter_dc(raw, DataclassType)` 过滤未知键
- 注意：`ScriptConfig` 使用显式 kwargs 构造，不需过滤；`_parse_providers`/`_parse_tasks` 用 `.get()` 安全读取

### 8.13 Provider 缓存与测试隔离

- `ai/factory.py` 的 `_provider_cache` 是模块级全局变量，跨测试持续存在
- 如果测试 A 缓存了一个 provider，测试 B 的 `monkeypatch` 修改配置后仍可能拿到旧 provider
- 修复：`_clear_provider_cache()` + `conftest.py` 的 `autouse` fixture 每个测试前自动清理

### 8.14 `retry_attempts` 语义

- `ProviderConfig.retry_attempts` 表示**额外重试次数**（不含首次），默认 `2`
- `with_retry(attempts=N)` 的 `attempts` 表示**总调用次数**（含首次）
- 转换公式：`with_retry(attempts=cfg.retry_attempts + 1)`
- 两个 provider（gemini + openai_compat）都用同一个公式，保持语义一致

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
