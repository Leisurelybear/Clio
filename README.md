# Vlog 剪辑辅助工具

旅行 vlog 剪辑前的 AI 预处理流水线：压缩素材 → 生成摘要与时间轴 → 口播文案 → 日 vlog 剪辑规划。

最终你在 **剪映** 等 App 里加特效、对口型/字幕即可。

[English](README.en.md)

---

## 功能概览

| 步骤 | 功能 | 命令 |
|------|------|------|
| 1 | 长视频压缩（去声音、控体积，供 AI 分析） | `compress` |
| 2 | AI 视频分析（简介 + 时间轴，厂家可配） | `analyze -i 文件夹` |
| 3 | 序号命名 + 文本文件 + CSV 汇总 | `analyze` 自动完成 |
| 4 | 按模板生成口播文案 | `scripts` |
| 5 | 推荐单日 vlog 片段顺序 | `plan --day day1` |
| 6 | 烧录序号便于剪映对照 | `label` |
| — | 一键全流程 | `run --day day1` |

---

## 快速开始

### 1. 一键配置环境

```powershell
cd G:\Coding_Project\IdeaProjects\vlog-video-analysis
.\setup.ps1
```

脚本会自动：

- 创建 `.venv` 虚拟环境并安装依赖
- 通过 winget 安装 ffmpeg（若未安装）
- 从 `.env.example` 创建 `.env`

### 2. 填写 API Key

编辑项目根目录的 `.env`：

```env
GEMINI_API_KEY=你的_Gemini_API_Key
```

> 也可设置系统环境变量，或在 `config.yaml` 的 `ai.providers` 中填写（不推荐提交到 git）。

### 3. 准备 config.yaml

```powershell
Copy-Item config.example.yaml config.yaml
# 然后用编辑器修改 paths.input_dir / proxy.url 等为你自己的值
```

### 4. 指定素材文件夹

**核心用法：输入是一个文件夹，程序批量分析其中所有视频。**

```powershell
# 指定素材文件夹（输出默认到 output/云南/）
python main.py analyze -i "E:/Videos/云南"

# 自定义输出目录
python main.py run -i "E:/Videos/云南" -o "./output/云南_v1" --day day1
```

也可在 `config.yaml` 设置默认 `paths.input_dir`，省略 `-i`。

### 5. 配置 AI 厂家与模型

每个步骤可独立配置厂家和模型（`config.yaml` → `ai`）：

```yaml
ai:
  providers:
    gemini:
      type: gemini
      api_key_env: GEMINI_API_KEY
    openai:
      type: openai
      api_key_env: OPENAI_API_KEY
      base_url: https://api.openai.com/v1
    deepseek:
      type: openai              # OpenAI 兼容 API
      api_key_env: DEEPSEEK_API_KEY
      base_url: https://api.deepseek.com/v1

  tasks:
    video_analyze:              # 视频理解（必须支持视频，如 gemini）
      provider: gemini
      model: gemini-2.5-flash
    voiceover:                  # 口播文案
      provider: deepseek
      model: deepseek-chat
    vlog_plan:                  # 日 vlog 规划
      provider: openai
      model: gpt-4o-mini
```

| 任务 | 说明 | 支持厂家 |
|------|------|----------|
| `video_analyze` | 看视频、输出时间轴 | `gemini` |
| `voiceover` | 生成口播文案 | `gemini` / `openai` / 任意 OpenAI 兼容 |
| `vlog_plan` | 推荐剪辑顺序 | 同上 |
| `refine_text` | 审阅修正已有素材分析/口播（`refine` 命令） | 同上（纯文本） |

> `refine_text` 默认回退到 `video_analyze` 的 provider。texts 和 scripts
> 审阅共用这一个任务（都是纯文本），在 `ai.tasks` 里显式声明可改成更便宜的模型。

### 6. 其他配置

编辑 `config.yaml`：

```yaml
paths:
  input_dir: "E:/Videos/云南"
  output_dir: "./output"
  recursive: false              # true = 扫描子文件夹

proxy:
  enabled: true
  url: "socks5://192.168.6.1:1080"
```

### 6.5 给 AI 加一段「行程背景/规范」

AI 偶尔会把素材误判成无关地点（比如把巴黎机场 RER 认成曼谷素万那普）。
在 `config.yaml` 里加 `ai.context` 或 `ai.context_file`，内容会作为**前言**自动注入到所有 AI 提示词前面：

```yaml
ai:
  context: "所有素材均拍摄于 2024 年 7 月法国巴黎，不要误判为其他城市。"
  # 或长文本用文件：
  # context_file: ./templates/trip_context.md
```

模板和示例见 `templates/trip_context.md`，建议至少写：

- 旅行时间 / 地点
- 命名约定（中文标题 vs. 外文原文）
- 容易误判的特例（如机场、地铁）
- 输出语言与风格

### 7. 检查环境

```powershell
.\.venv\Scripts\Activate.ps1
python main.py check
```

全部显示 `[OK]` 后即可运行。

### 8. 运行

```powershell
# 分析指定文件夹（最常用）
python main.py analyze -i "E:/Videos/云南"

# 一键全流程
python main.py run -i "E:/Videos/云南" --day day1

# 或分步执行
python main.py analyze          # 压缩 + AI 分析
python main.py scripts          # 口播文案
python main.py plan --day day1  # 日 vlog 规划
python main.py label            # 烧录序号
```

> 重复执行会**自动跳过已生成的素材**（读取 `config.yaml` 的 `skip_existing`），可以从中断处继续。
> 想要强制重跑某个步骤时加 `--force`：
> ```powershell
> python main.py analyze --force
> ```

### 9. 查看运行日志

所有 CLI 运行的 `print()` / 错误信息会**同时**写到控制台和 `logs/` 目录。
日志按小时切分，文件名格式：`logs/YYYY-MM-DD-HH.log`（如 `logs/2026-06-06-14.log`）。
跨小时的长时间任务会自动切到新文件，无需重启。

```powershell
# 看最近一次运行的日志
Get-Content (Get-ChildItem logs/*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1) -Tail 50
```

日志目录可通过 `config.yaml` 的 `paths.logs_dir` 修改。日志**不**提交到 git（已在 `.gitignore`）。

---

## 输出目录结构

```
output/
├── compressed/          # 压缩版视频（给 AI 用，已去声音）
├── texts/
│   ├── 001_丽江古城.txt    # 人类可读：简介 + 时间轴
│   └── 001_丽江古城.json   # 机器可读，供后续步骤使用
├── scripts/
│   ├── 001_丽江古城_voiceover.md   # 口播文案（可直接用于剪映）
│   └── 001_丽江古城_voiceover.json
├── labeled/             # 烧录了序号的预览视频
├── plans/
│   ├── day1_plan.md     # 推荐剪辑顺序与时间轴
│   └── day1_plan.json
└── summary.csv          # 所有素材总览表
```

---

## 典型工作流

```
原始素材 (input_dir)
    │
    ▼ compress + analyze
压缩视频 + 文本/CSV
    │
    ├──► scripts ──► 口播文案（每条素材一份）
    │
    ├──► plan ────► 日 vlog 剪辑方案（选哪些片段、什么顺序）
    │
    └──► label ───► 带序号的预览视频（剪映对照用）
    │
    ▼
用户在剪映中：按 plan 选片段 → 加特效 → 粘贴口播文案
```

---

## 配置说明

### 压缩参数 (`compress`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `target_size_mb` | 5 | 目标体积（MB），按视频时长自动算码率 |
| `max_width` | 640 | 最大宽度 |
| `fps` | 15 | 帧率 |
| `remove_audio` | true | 去除声音 |

### AI 参数 (`gemini`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `model` | gemini-2.5-flash | 分析/文案模型 |
| `poll_interval_sec` | 5 | 上传后等待处理完成的轮询间隔 |

### 口播模板

编辑 `templates/vlog_template.md` 可调整口播风格（第一人称、字数、结构等）。

---

## 命令参考

所有子命令的完整说明。短形式仅列高频用法。

### 全局参数

| 参数 | 适用范围 | 说明 |
|------|----------|------|
| `-c, --config <文件>` | 全部 | 配置文件路径（默认 `config.yaml`） |
| `-i, --input <路径>` | 多数子命令 | 素材文件夹 / 单个 json / json 目录（覆盖 config.yaml） |
| `-o, --output <路径>` | 多数子命令 | 输出目录（默认 `output/<素材文件夹名>`） |
| `--force` | 全部 | 忽略已存在的输出，强制重新生成（覆盖 `analyze.skip_existing`） |

### `check` — 环境检查

验证虚拟环境、ffmpeg / ffprobe、素材目录、每个 AI 任务的 API key 是否就绪。
不会发起任何网络请求。

```powershell
python main.py check
python main.py check -i "E:/Videos/云南"     # 同时验证指定素材目录
```

输出 `[OK] xxx` 或 `[FAIL] xxx`，以及发现多少个视频文件。

### `compress` — 仅压缩

把素材文件夹中的视频用 ffmpeg 压成 640p / 5MB / 去声音的 mp4 备用。
**不**调 AI。适合想先批量压缩、再人工筛选的场景。

```powershell
python main.py compress -i "E:/Videos/云南"
```

输出到 `output/<素材文件夹名>/compressed/`，命名格式 `<序号>_<原文件名>.mp4`（如 `001_GL010683.mp4`）。
已经存在的压缩文件会自动跳过（`skip_existing: true` 时）。

### `analyze` — 压缩 + AI 分析（最常用）

先压缩（如果还没压缩），再对每条压缩视频调 `ai.tasks.video_analyze` 配置的厂家（默认 Gemini）做内容分析。

```powershell
python main.py analyze -i "E:/Videos/云南"
python main.py analyze --force     # 强制重新分析（覆盖 skip_existing）
```

输出三件套：
- `output/<素材文件夹名>/texts/<序号>_<标题>.json` — 结构化分析（机器可读）
- `output/<素材文件夹名>/texts/<序号>_<标题>.txt` — 人类可读版（含时间轴）
- `output/<素材文件夹名>/summary.csv` — 全素材总览表（一行一条）

> 重复执行会**自动跳过**已生成的 `.json` / `.txt`（`analyze.skip_existing: true` 时）。
> 想全部重跑加 `--force`。

### `scripts` — 生成口播文案

对 `texts/` 里的每条分析，调 `ai.tasks.voiceover` 厂家（默认 DeepSeek）按
`templates/vlog_template.md` 模板生成口播文案。

```powershell
python main.py scripts
```

输出到 `output/<素材文件夹名>/scripts/<序号>_<标题>_voiceover.{json,md}`。
`.md` 是可以直接粘进剪映的成稿。

### `plan` — 日 vlog 剪辑规划

把当天所有 `texts/` 摘要给 `ai.tasks.vlog_plan` 厂家，让它挑出最有叙事感的若干片段排成剪辑顺序。

```powershell
python main.py plan --day day1
python main.py plan --day "Day2_卢瓦尔河谷"
```

`--day` 标签会出现在输出文件名和 vlog 标题里。输出到 `output/<素材文件夹名>/plans/<day>_plan.{json,md}`。

### `label` — 烧录序号标注

在压缩视频左上角烧录序号（`001` / `002` / ...），便于剪映里对照 plan 选片段。

```powershell
python main.py label
```

输出到 `output/<素材文件夹名>/labeled/<序号>_<标题>_labeled.mp4`。

### `run` — 一键全流程

依次跑 `analyze` → `scripts` → `plan` → `label`，中间任何一步都可单独重跑。

```powershell
python main.py run -i "E:/Videos/云南" --day day1
```

### `refine` — 审阅修正已有输出

`refine` 有两种模式：

#### 1. 审阅模式（默认）

AI 依据 `ai.context` / `ai.context_file` 自动审阅并修正错误（地点误判、命名不一致等）。

```powershell
# 默认：审阅 texts/ 和 scripts/ 下的所有文件
python main.py refine

# 只审阅 texts/
python main.py refine --target texts

# 修正单个文件
python main.py refine -i output/Franch/texts/001_机场轻轨清晨.json

# 修正某个文件夹下的所有 json
python main.py refine -i output/Franch/texts/
```

#### 2. 定向修正模式（`--fix`）

你给一句具体修改意见，AI **只改**这条意见提到的字段，其它一字不动。
必须配合 `-i` 指定单个文件，避免误伤。

```powershell
# 把 location 字段从误判改成正确地名
python main.py refine -i output/Franch/texts/001_机场轻轨清晨.json `
    --fix "把 location 从曼谷素万那普机场改成巴黎戴高乐机场"

# 修正 voiceover 文案里的具体错误
python main.py refine -i output/Franch/scripts/001_机场轻轨清晨_voiceover.json `
    --fix "把 voiceover 第一句'曼谷的早晨'改成'巴黎的早晨'"
```

`_changelog` 字段的第一条会写"按用户意见修改了 XXX"，方便审计。
两种模式都会调用 `video_analyze` 任务的 AI（默认 gemini）审 texts、
`voiceover` 任务的 AI（默认 deepseek）审 scripts，结果直接覆盖原文件。

---

## 常见问题

### `找不到 ffmpeg`

1. 运行 `.\setup.ps1` 自动安装
2. 或手动安装后在 `config.yaml` 填写：
   ```yaml
   paths:
     ffmpeg: "C:/path/to/ffmpeg.exe"
     ffprobe: "C:/path/to/ffprobe.exe"
   ```

### `socksio package is not installed`

确保在虚拟环境中安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### `File is not in an ACTIVE state`

视频上传后需等待 Google 处理。工具已内置轮询；若仍失败，稍后重试。

### `ConnectTimeout` / 网络错误

确认代理可用，检查 `config.yaml` 中 `proxy.url` 是否正确。

### pip 安装失败（系统 Python 权限问题）

**务必使用项目虚拟环境**，不要直接用全局 `pip`：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 重新分析某个视频

删除 `output/texts/` 中对应的 `.txt` 和 `.json`，或将 `analyze.skip_existing` 设为 `false`。

---

## 项目结构

```
vlog-video-analysis/
├── config.example.yaml  # 配置模板（提交到 git）
├── config.yaml          # 实际配置（不提交 git，本地 cp 自 example）
├── .env                 # API Key（不提交 git）
├── setup.ps1            # 一键环境配置
├── main.py              # CLI 入口
├── templates/
│   └── vlog_template.md # 口播风格模板
└── vlog_tool/
    ├── ai/              # AI 厂家抽象（gemini / openai 兼容）
    ├── compress.py
    ├── analyze.py
    ├── pipeline.py
    └── prompts.py
```

---

## 依赖

- Python 3.11+
- ffmpeg / ffprobe
- Gemini API Key
- SOCKS5 代理（国内环境）

---

## 后续可扩展

- [ ] 按文件夹/日期自动分组多天 vlog
- [ ] 剪映草稿导出格式
- [ ] Web UI 预览时间轴
- [ ] 支持 Whisper 本地语音转写（有口播的素材）
