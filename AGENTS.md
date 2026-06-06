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
│   ├── utils.py               # ffmpeg 路径发现、文件 IO、mask_if_looks_like_key
│   └── ai/
│       ├── base.py            # TaskName 枚举、Provider Protocol
│       ├── factory.py         # 按名字查找 provider
│       ├── gemini.py          # 多模态：File API 上传 + 轮询 PROCESSING
│       └── openai_compat.py   # OpenAI 兼容：DeepSeek / OpenAI / 通义 / Moonshot
├── templates/
│   ├── vlog_template.md       # 口播风格模板（用户可改）
│   └── trip_context.md        # trip 背景与 AI 规范（自动注入到所有 prompt）
├── config.example.yaml        # 提交到 git 的配置模板
├── .env.example               # 提交到 git 的环境变量模板
├── config.yaml / .env         # 用户本地真实配置，gitignore
├── setup.ps1                  # 一键环境
├── README.md / README.en.md   # 用户文档（双语）
└── AGENTS.md                  # 本文件
```

## 4. 关键约定

### 4.1 Commit

- **英文** message，**Conventional Commits** 风格：`type(scope): subject`
- **一个功能一个 commit**（用户明确要求；不要把多个独立功能合在一起）
- 常见 type：`feat` / `fix` / `refactor` / `docs` / `chore`
- rebase 改历史时优先用 `git rebase -i --root`；Windows 下交互式 editor 容易卡，用 `git filter-branch --msg-filter` 走字节级 Python 脚本（见 [§8 Gotchas](#8-gotchas)）

### 4.2 代码风格

- 不要写注释，除非解释**为什么**（WHAT 自己看得见）
- 中文 user-facing 文案（CLI 提示、错误信息、README 中文版）
- 默认 `skip_existing=True` 的策略被所有 step 共享（改 `analyze` 这一个开关就行）
- AI 返回的 JSON 用 `extract_json()` 容错（先 `json.loads`，再正则抓 `{}`）

### 4.3 配置

- 仓库提交 `config.example.yaml` 和 `.env.example`；真实 `config.yaml` 和 `.env` 在 `.gitignore` 里
- 任何含**本地路径、代理 IP、API key** 的字段都不要进 example（用占位符）
- 配置文件改动后建议同时更新 example 和 README/en

### 4.4 提示词

- 全部放在 `vlog_tool/prompts.py`，用常量
- trip 上下文通过 `_wrap_with_context()` 在所有 prompt 前面统一注入；**不要**在每个 prompt 里手写 prefix
- 输出格式必须是 JSON（不是 markdown 代码块），`extract_json()` 才能解析

## 5. 添加新功能的标准做法

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

`refine_text` 默认回退到 `video_analyze`、`refine_script` 默认回退到 `voiceover`
（逻辑在 `vlog_tool/config.py:_parse_tasks`）。要切到更便宜的纯文本模型，
在 `ai.tasks` 里显式加：

```yaml
ai:
  tasks:
    refine_text:
      provider: deepseek
      model: deepseek-chat
    refine_script:
      provider: deepseek
      model: deepseek-chat
```

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

## 7. 项目当前状态

最后更新：见 `git log --oneline -10`。
最近做的 7 个 commit 顺序：
1. `chore: scaffold initial Vlog editing helper project`
2. `fix(compress): escape comma in scale expression`  ← Windows ffmpeg filter 逗号转义
3. `feat(pipeline): make all steps resume-safe`  ← skip_existing 真接上
4. `docs: add English README and link from Chinese README`
5. `fix(ai): clearer error when API key is missing or misconfigured`  ← 防止 key 被回显
6. `feat(ai): support per-trip context preamble`  ← ai.context / ai.context_file
7. `feat(cli): add refine subcommand to polish existing outputs`  ← 用 trip context 修正旧输出
8. `docs: add AGENTS.md`  ← AI 维护手册
9. `feat(ai): independent provider for refine tasks`  ← refine_text / refine_script 可独立配

用户当前行程：**2025 年国庆节法国巴黎 7 日自由行**（`templates/trip_context.md`）
已知 AI 误判坑：把戴高乐机场 RER 认成曼谷素万那普 → context 第 5 节已写明。

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
