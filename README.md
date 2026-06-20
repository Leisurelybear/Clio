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
| 2 | AI 视频分析（简介 + 时间轴，厂家可配） | `analyze` |
| 3 | 序号命名 + 文本文件 + CSV 汇总 | `analyze` 自动完成 |
| 4 | 按模板生成口播文案 | `scripts` |
| 5 | 推荐单日 vlog 片段顺序 | `plan --day day1` |
| 6 | 烧录序号便于剪映对照 | `label` |
| 7 | 离线语音识别（ASR）转录 | `transcribe` |
| 8 | 按规划裁剪视频片段 | `cut --day day1` |
| — | 一键全流程 | `run --day day1` |
| — | 可视化 Web UI 编辑器 | `serve` |
| — | 环境检查 | `check` |

---

## 可视化编辑 UI

`serve` 子命令启动一个本地 Web 服务，默认 `http://127.0.0.1:8765/`：

| 流水线执行界面 | vlog 剪辑规划界面 |
|:---:|:---:|
| ![pipeline](docs/screenshots/pipeline.png) | ![plan](docs/screenshots/plan.png) |

- 左侧：视频列表，每条标注是否已有分析/口播 JSON
- 中间：HTML5 播放器，支持拖动 / 跳跃 / Range 请求
- 右侧：分析、口播、规划三个 Tab，可编辑 AI 输出并保存

零外部依赖（纯 stdlib `http.server`），安全绑定 127.0.0.1。
详细说明见 `vlog_tool/ui/README.md`。

---

## 快速开始

### 1. 配置环境

```bash
# Windows
.\setup.ps1

# Linux / macOS
./setup.sh
```

脚本自动创建虚拟环境、安装依赖、安装 ffmpeg、从 `.env.example` 创建 `.env`。

### 2. 填写 API Key

编辑 `.env`，填入你的 API Key：

```env
GEMINI_API_KEY=你的_Gemini_API_Key
```

也可设置系统环境变量，或在 `config.yaml` 的 `ai.providers` 中填写。

### 3. 准备配置文件

```bash
cp config.example.yaml config.yaml
# 然后修改 paths.input_dir、proxy.url 等
```

### 4. 运行分析

```bash
# 分析指定文件夹
python main.py analyze -i "E:/Videos/云南"

# 或一键全流程
python main.py run -i "E:/Videos/云南" --day day1
```

重复执行会自动跳过已生成的素材。加 `--force` 强制重跑。

### 5. 查看日志

所有输出同时写入控制台和 `logs/` 目录（按小时切分），查看最近日志：

```bash
# Windows (PowerShell)
Get-Content (Get-ChildItem logs/*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1) -Tail 50

# Linux / macOS
ls -t logs/*.log | head -1 | xargs tail -50
```

> 完整配置说明（AI 厂家、压缩参数、项目专属配置）和全部 CLI 子命令参考见 [docs/cli-reference.md](docs/cli-reference.md)。

---

## 常用命令速览

```bash
python main.py check                          # 环境检查
python main.py analyze -i "E:/Videos/云南"    # 压缩 + AI 分析
python main.py scripts                        # 生成口播文案
python main.py plan --day day1                # vlog 剪辑规划
python main.py label                          # 烧录序号
python main.py cut --day day1                 # 按规划裁剪
python main.py serve                          # 启动 Web UI
python main.py refine                         # AI 审阅修正已有输出
python main.py transcribe                     # 离线语音转录
```

> 每个子命令的全部 flag 和示例见 [docs/cli-reference.md](docs/cli-reference.md)。

---

## 常见问题

### 找不到 ffmpeg

1. 运行 `setup.ps1`（Windows）或 `setup.sh`（Linux/Mac）自动安装
2. 或手动安装后在 `config.yaml` 填写路径

### socksio package is not installed

```bash
python -m pip install -r requirements.txt
```

### File is not in an ACTIVE state

视频上传后需等待 Google 处理。工具已内置轮询；若仍失败，稍后重试。

### ConnectTimeout / 网络错误

确认代理可用，检查 `config.yaml` 中 `proxy.url`。

### pip 安装失败

务必使用项目虚拟环境（Windows: `.venv\Scripts\activate`, Linux/Mac: `source .venv/bin/activate`）：

```bash
python -m pip install -r requirements.txt
```

### 重新分析某个视频

删除 `output/texts/` 中对应的 `.txt` 和 `.json`，或设置 `analyze.skip_existing: false`。

---

## 参与开发

本项目是个人 vlogger 工具，欢迎提交 Issue 和 PR。

- 开发文档（项目结构、设计决策、代码约定）：[AGENTS.md](AGENTS.md)
- 需求追踪 / 路线图：[ROADMAP.md](ROADMAP.md)
- 完整 CLI 参考：[docs/cli-reference.md](docs/cli-reference.md)
- 运行测试：`python -m pytest vlog_tool/tests/ -v`
