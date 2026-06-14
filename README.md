[![CI](https://github.com/Leisurelybear/vlog-editing-helper/actions/workflows/test.yml/badge.svg)](https://github.com/Leisurelybear/vlog-editing-helper/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/Leisurelybear/vlog-editing-helper/graph/badge.svg?token=CODECOV_TOKEN)](https://codecov.io/gh/Leisurelybear/vlog-editing-helper)

# Vlog 剪辑辅助工具

旅行 vlog 剪辑前的 AI 预处理流水线：压缩素材 → 生成摘要与时间轴 → 口播文案 → vlog 剪辑规划。

最终你在 **剪映** 等 App 里加特效、对口型/字幕即可。

[English](README.en.md)

---

## 功能概览

| 步骤 | 功能 | 命令 |
|------|------|------|
| 1 | 长视频分割 + 压缩（去声音、控体积，供 AI 分析） | `compress` |
| 2 | AI 视频分析（简介 + 时间轴，厂家可配） | `analyze -i 文件夹` |
| 3 | 序号命名 + 文本文件 + CSV 汇总 | `analyze` 自动完成 |
| 4 | 按模板生成口播文案 | `scripts` |
| 5 | 推荐单日 vlog 片段顺序 | `plan --day day1` |
| 6 | 烧录序号便于剪映对照 | `label` |
| 7 | 离线语音识别（ASR）转录 | `transcribe` |
| 8 | 按规划裁剪视频片段 | `cut --day day1 -o ./my_clips` |
| — | 一键全流程 | `run --day day1` |
| — | 可视化 Web UI 编辑器 | `serve` |
| — | 环境检查 | `check` |

---

## 可视化编辑 UI

`serve` 子命令会启动一个本地 Web 服务，默认 `http://127.0.0.1:8765/`：

| 流水线执行界面 | vlog 剪辑规划界面 |
|:---:|:---:|
| ![pipeline](docs/screenshots/pipeline.png) | ![plan](docs/screenshots/plan.png) |

- 左侧：视频列表（自动扫描 `output/compressed/`），每条标注是否已有 `texts` / `voiceover` JSON
- 中间：HTML5 视频播放器（支持拖动 / 跳跃），点右侧 segment 自动跳转
- 右侧：三个 Tab
  - **分析 (texts)** — 编辑 `title` / `location` / `mood` / `summary`，每段 timeline 描述
  - **口播 (scripts)** — 编辑 `voiceover` 文案 / `edit_tip` / `duration_hint_sec`
  - **vlog 剪辑规划 (plan)** — 编辑剪辑主题、起止提示、每段 `sequence` 的 `reason` / `voiceover_hint`

修改后点 "保存" 或按 `Ctrl+S` 写回原文件（atomic rename + 每次覆盖留 `.bak`）。

零外部依赖：纯 stdlib `http.server`，不需要 Flask / FastAPI。安全：默认仅监听 127.0.0.1，所有文件 IO 沙盒在 `output_dir` 内，basename 不允许 `..` 或路径分隔符。

详细文档见 `vlog_tool/ui/README.md`。

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
python main.py plan --day day1  # vlog 剪辑规划（基于素材分析结果生成编排方案）
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
├── splits/              # 长视频分割后的分段（默认 15 分钟以上分割）
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
├── cuts/
│   └── day1/            # 裁剪出来的片段 + manifest.md
└── summary.csv          # 所有素材总览表
```

---

## 典型工作流

```
原始素材 (input_dir)
    │
    ├── 长视频（>15分）→ split ───► splits/_segNN 分段
    │
    ▼ compress
640p 压缩视频 (compressed/)
    │
    ▼ analyze (Gemini)
文本分析 (texts/)
    │
    ├──► scripts ──► 口播文案（每条素材一份）
    │
    ├──► plan ────► 日 vlog 剪辑方案（选哪些片段、什么顺序）
    │
    ├──► label ───► 带序号的预览视频（剪映对照用）
    │
    ├──► cut ─────► 按 plan 裁剪出片段 + manifest.md
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

### AI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| （见 `config.example.yaml` 的 `ai` 段） | — | 每个任务可独立指定 provider 和 model |

### 项目专属配置 (`project.yaml`)

每个项目目录下可以放一个 `project.yaml`，只需写与全局 `config.yaml` **不同的字段**：

```yaml
# 例：巴黎项目使用专属 AI context 和压缩参数
ai:
  context_file: ./trip_context_paris.md
compress:
  fps: 1
  target_size_mb: 5
```

加载时自动 deep-merge 到全局配置之上：
- 嵌套字典递归合并（如 `ai.tasks`），不会覆盖整个块
- 未覆盖的字段继承全局 `config.yaml`
- `ai.context_file` 相对路径优先按项目目录解析
- UI 设置 tab 通过 `?project=X` 自动读写当前项目的 `project.yaml`
- CLI 目前通过 `--input` 覆盖目录，后续将支持 `--project`

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

分两个阶段：
1. **分割（Phase 1）**：长视频（默认 > 15 分钟）先按关键帧切割成 `_segNN` 段，存到 `splits/`
2. **压缩（Phase 2）**：对每个分割段（以及无需分割的短视频）逐条压缩到 `compressed/`

```powershell
python main.py compress -i "E:/Videos/云南"

# 只处理单个视频文件
python main.py compress -i "E:/Videos/云南/GL010683.mp4"
```

输出到 `output/<素材文件夹名>/compressed/`，命名格式 `<序号>_<原文件名>.mp4`（如 `001_GL010683.mp4`）。
分段视频会按原文件名分组显示，格式如 `001_GL010683.mp4`（含 `001_GL010683_seg00.mp4` 等子项）。
已经存在的压缩文件会自动跳过（`skip_existing: true` 时）。

### `analyze` — 压缩 + AI 分析（最常用）

先压缩（如果还没压缩），再对每条压缩视频调 `ai.tasks.video_analyze` 配置的厂家（默认 Gemini）做内容分析。
超过 `max_analyze_duration_min`（默认 30 分钟）的视频会**跳过**（AI 通不过配额限制）。

```powershell
python main.py analyze -i "E:/Videos/云南"
python main.py analyze --force         # 强制重新分析（覆盖 skip_existing）

# 只分析单个视频
python main.py analyze -i "E:/Videos/云南/GL010683.mp4"
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

# 只生成单条分析的口播
python main.py scripts -i output/Franch/texts/001_机场轻轨清晨.json
```

输出到 `output/<素材文件夹名>/scripts/<序号>_<标题>_voiceover.{json,md}`。
`.md` 是可以直接粘进剪映的成稿。

### `plan` — vlog 剪辑规划

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

### `cut` — 按规划裁剪视频片段

读取 `plans/<day>_plan.json`，按 `sequence[].use_timeline` 指定的时间范围，
从对应压缩视频（或原片）中用 ffmpeg 裁剪出独立片段。

```powershell
# 默认输出到 output/cuts/day1/
python main.py cut --day day1

# 指定输出目录
python main.py cut --day day1 --out-dir "E:/剪辑素材/第一天"

# 从原片裁剪（而非压缩版）
python main.py cut --day day1 --source original

# 重新编码（默认 -c copy 几秒完成；启用则 h264 精确剪）
python main.py cut --day day1 --reencode
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--day` | `day1` | 规划标签（对应 `plans/<day>_plan.json`） |
| `--out-dir` | `output/cuts/<day>/` | 输出目录，用户可任意指定 |
| `--source` | `compressed` | 视频来源：`compressed`（压缩版）或 `original`（原片） |
| `--reencode` | — | h264 重新编码（默认 `-c copy` 快剪） |

输出每个片段为 `<序号>_<标题>_seg_<编号>.mp4`，如果有对应的 `texts JSON` 也会复制到同目录。
完成后生成 `manifest.md`（markdown 表格，含每个片段的信息）。

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

#### 3. 临时上下文模式（`--context / -C`）

临时追加一条上下文说明，附加在 `ai.context` 之后、优先级更高。
适合临时纠正某个常见错误，不改 `config.yaml`：

```powershell
python main.py refine --context "特别注意：所有素材均在法国巴黎拍摄，不要误判为其他城市"

# 也可与 --fix 组合
python main.py refine -i output/Franch/scripts/001_机场轻轨清晨_voiceover.json `
    --fix "把 location 改成巴黎戴高乐机场" `
    --context "用户刚从泰国回来，AI 请勿混淆曼谷和巴黎"
```

---

### 转录 → `transcribe` / `whisper`

使用 faster-whisper 对视频进行离线语音识别（ASR），生成带时间戳的文字转录。先执行 `whisper install` 安装依赖，再执行 `transcribe`。

```bash
# 安装 faster-whisper（含 CUDA 检测与模型预下载）
python main.py whisper install

# 检测 faster-whisper / CUDA / 模型缓存状态
python main.py whisper check

# 对已压缩的视频进行语音转录
python main.py transcribe

# 忽略已有转录，全部重新生成
python main.py transcribe --force
```

> 提示：transcript 数据会注入到 `plan` 的 prompt 中，AI 会参考实际口播内容来优化剪辑编排。

---

### `serve` · 启动本地 Web UI（可视化编辑）

启动一个浏览器里的可视化编辑器，看视频 + 改 AI 输出（texts / scripts / plan），直接保存回 JSON。

```bash
python main.py serve                    # 默认 http://127.0.0.1:8765/，自动开浏览器
python main.py serve --port 9000        # 换端口
python main.py serve --no-browser       # 不自动开浏览器（远程机调试用）
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 监听地址；改 `0.0.0.0` 可暴露到局域网（注意安全） |
| `--port` | `8765` | 端口 |
| `--no-browser` | — | 加上则不自动打开浏览器 |

启动后打开的页面：左侧视频列表（自动扫描 `output/compressed/`），中间是视频播放器（支持拖动 / Range 请求），右侧三个 Tab：分析（texts）、口播（scripts）、vlog 剪辑规划（plan）。点 timeline / plan 里的 segment 自动跳到对应时间；`Ctrl+S` 保存。
详见 `vlog_tool/ui/README.md`。


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
├── config.example.yaml   # 配置模板（提交到 git）
├── config.yaml           # 实际配置（不提交 git，本地 cp 自 example）
├── .env                  # API Key（不提交 git）
├── requirements.txt           # 开发期宽松依赖
├── requirements-locked.txt    # 可重现构建锁定版本
├── setup.ps1             # 一键环境配置
├── main.py               # CLI 入口
├── .github/workflows/    # GitHub Actions CI
├── vlog_tool/tests/      # 单元测试（381 用例）
├── templates/
│   ├── vlog_template.md  # 口播风格模板
│   └── trip_context.md   # 旅行背景与 AI 规范
└── vlog_tool/
    ├── _constants.py     # 全局常量
    ├── ai/               # AI 厂家抽象（gemini / openai 兼容）
    ├── config.py         # 配置解析
    ├── compress.py       # ffmpeg 压缩
    ├── split.py          # 视频分段切割
    ├── analyze.py        # AI 分析调用
    ├── cut.py            # 视频裁剪
    ├── log.py            # 日志系统
    ├── progress.py       # 进度追踪
    ├── prompts.py        # AI Prompt 模板
    ├── utils.py          # 通用工具
    ├── tasks/            # 流水线步骤（拆分自 pipeline.py）
    │   ├── compress.py / analyze.py / scripts.py
    │   ├── plan.py / label.py / cut.py / refine.py
    │   └── _helpers.py
    ├── pipeline.py       # 编排层（~96 行）
    ├── tests/            # 单元测试（381 用例）
    └── ui/               # 本地 Web UI（拆分自 server.py）
        ├── server.py     # 分发层（~454 行）
        ├── routes/       # 路由处理（videos / projects / texts / plan / config / run / fs）
        ├── services/     # 业务服务（file_service / project_service）
        └── static/       # 前端
            ├── index.html / style.css
            ├── app.js    # ES module entry
            └── src/      # ES 模块（state / utils / api / viewer / editor / runner / sidebar / main）
```

---

## 依赖

- Python 3.11+
- ffmpeg / ffprobe
- Gemini API Key
- SOCKS5 代理（国内环境）

## 测试

项目包含 **381 个 pytest 单元测试**，覆盖核心纯函数、路由 handler、辅助函数和编排逻辑：

| 模块 | 用例数 | 覆盖内容 |
|------|--------|----------|
| `test_config.py` | 34 | 配置加载 / deep-merge / 校验 |
| `test_utils.py` | 34 | extract_json / mask_if_looks_like_key / sanitize_name / find_videos |
| `test_cut.py` | 25 | 时间解析 / 文件名生成 |
| `test_log.py` | 13 | TeeWriter / timed / format_size / format_duration |
| `test_progress.py` | 12 | ProgressTracker 读写与初始化 |
| `test_ai.py` | 12 | factory dispatch / provider 实例化 / TaskName |
| `test_analyze.py` | 10 | `_resolve_original` 文件匹配 |
| `test_analyze_funcs.py` | 9 | `_wrap_with_context` / `plan_daily_vlog` 过滤 |
| `test_split.py` | 7 | `split_video` segment 计算 |
| `test_compress.py` | 6 | `compress_video` 码率 / 参数 |
| `test_file_service.py` | 60 | 安全 basename / atomic save / segment 匹配 / config 类型转换 |
| `test_helpers.py` | 20 | `_next_index` / `_write_csv` / `_rewrite_text_file` |
| `test_project_service.py` | 22 | output dir / registry / step detection |
| `test_routes_*.py` | 48 | 视频 / 计划 / 配置 / 运行 / 项目 / 转录路由 handler |
| `test_tasks_*.py` | 12 | `run_compress_all` / `run_analyze_all` / `run_transcribe_all` 编排 |
| `test_transcribe.py` | 15 | transcribe 开关 / enabled / deps 检测 |
| `test_routes_transcripts.py` | 7 | transcript / whisper API 路由 |

每次推送到 main 或提 PR 时，GitHub Actions 自动在 Python 3.11 / 3.12 上运行测试。

```bash
# 本地运行
pip install pytest
python -m pytest vlog_tool/tests/ -v
```

```bash
# 运行单个测试模块
python -m pytest vlog_tool/tests/test_utils.py -v
```

### 代码格式化

本项目使用 `ruff` 做 lint 和格式化。项目包含 pre-commit hook，提交前自动格式化：

```bash
# 启用 hook（首次克隆后执行一次即可）
git config core.hooksPath .githooks
```

Hook 会在每次 `git commit` 前自动运行 `ruff format` 并重新 stage 格式化后的文件。

### 依赖版本锁定

`requirements-locked.txt` 记录了精确版本号，用于 CI 和可重现构建。
日常开发使用宽松版本的 `requirements.txt`。

---

## 后续可扩展

- [x] 视频分段：长视频自动分割后再压缩（默认 15 分钟阈值）
- [x] Web UI 侧栏分层：项目 / 视频两级层级（R-006）
- [x] 多项目切换：侧栏下拉切换项目，URL 参数持久化（R-007）
- [x] 流水线进度：运行 tab + ProgressTracker 实时进度轮询（R-005）
- [x] 裁剪：按规划一键裁剪视频片段（R-002，含 CLI + UI）
- [x] 分布式改进：server.py / app.js 拆模块（Phase 1a~1d）
- [ ] 按文件夹/日期自动分组多天 vlog
- [ ] 剪映草稿导出格式
- [ ] Web UI 预览时间轴（R-012）
- [ ] Web UI 单步执行：选目录 → 选文件 → 跑步骤 → 进度 → 自动刷新（R-008）
- [x] 支持 Whisper 本地语音转写（有口播的素材）（R-013）
- [ ] AI token 用量统计面板（R-014）
