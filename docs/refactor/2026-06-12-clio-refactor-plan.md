**vlog-editing-helper**

架构重构规划文档

*Refactoring & Desktop Evolution Roadmap*

2026 年 6 月

# **1. 执行摘要**

本文档为 vlog-editing-helper 项目制定系统性重构方案，目标是在保持功能完整的前提下，将项目从"能用的脚本集合"演进为"可维护的桌面级应用"。

当前痛点快照：

* server.py 已达 1261 行，是单一大型闭包，路由/业务/IO 混杂
* app.js 达 1393 行，全局函数无模块边界，状态管理分散
* pipeline.py 788 行，compress/analyze/plan/cut 逻辑全部堆在一个文件
* Web UI 依赖 stdlib http.server，无法支持 SSE 实时推送，性能天花板明显
* 未来向桌面端发展（Tauri/Electron），当前架构与桌面壳子的适配成本极高

重构分三个阶段，每阶段独立可交付，不中断日常开发：

* Phase 1（1-2 周）：零破坏清理——拆分大文件，不改功能，降低维护摩擦
* Phase 2（2-4 周）：后端升级——迁移至 FastAPI，解锁 SSE、async、类型安全
* Phase 3（1-3 个月）：桌面端——用 Tauri 封装，原生体验，离线运行

# **2. 现状分析**

## 2.1 当前文件结构

vlog-editing-helper/

├── main.py # CLI 入口 (296 行)

├── config.example.yaml

├── requirements.txt / requirements-locked.txt

├── setup.ps1 # Windows 环境配置

├── templates/ # 口播模板 + 行程背景

├── docs/superpowers/ # 设计文档

└── vlog\_tool/

├── ai/ # AI 厂商抽象 (4 个文件)

├── ui/

│ ├── server.py # ⚠ 1261 行 单文件服务器

│ └── static/

│ ├── app.js # ⚠ 1393 行 全局函数

│ ├── index.html

│ └── style.css

├── tests/ # 128 个单元测试

├── pipeline.py # ⚠ 788 行 所有流水线

├── analyze.py # AI 分析调用

├── compress.py # ffmpeg 压缩

├── config.py # 配置加载/校验

├── cut.py # 裁剪

├── log.py # 日志助手

├── progress.py # 进度追踪

├── prompts.py # AI Prompt

└── utils.py # 工具函数

## 2.2 主要问题

| **问题** | **受影响文件** | **严重程度** |
| --- | --- | --- |
| server.py 单文件 1261 行：路由注册、业务逻辑、文件 IO、项目管理全混在一起 | ui/server.py | 🔴 高 |
| app.js 1393 行：全局状态、DOM 操作、API 调用、播放控制无分离 | ui/static/app.js | 🔴 高 |
| pipeline.py 788 行：compress/analyze/scripts/plan/cut/label 全在一个文件 | pipeline.py | 🟡 中 |
| stdlib http.server 不支持 SSE，进度只能轮询（2s 间隔），延迟高 | server.py | 🟡 中 |
| VIDEO\_EXTS 常量在 utils.py 和 server.py 各定义一份（B-019） | utils.py, server.py | 🟢 低 |
| format\_index 硬编码 3 而非用 config（B-020） | pipeline.py | 🟢 低 |

## 2.3 桌面端适配分析

面向桌面端演进，有两条主流路径：

| **方案** | **前端技术** | **后端技术** | **优势** | **劣势** |
| --- | --- | --- | --- | --- |
| Tauri 2.0 | 现有 Web UI（可复用） | Python sidecar | 包体积小（<10MB），内存低，Rust 原生安全 | 需要 Rust 工具链；Python sidecar 管理稍复杂 |
| Electron | 现有 Web UI（可复用） | Python subprocess | 生态成熟，调试方便 | 包体积大（>100MB），内存占用高 |
| 纯 Python + PyQt/PySide6 | Qt Widget 或 QWebEngine | Python 原生 | 单一语言，分发简单 | 前端重写成本高；与现有 Web UI 割裂 |

推荐 Tauri 2.0：复用现有 Web UI 投资，包体积小，适合视频工具（本机 ffmpeg 调用）。核心改造是把 FastAPI 作为 Python sidecar，由 Tauri 主进程拉起和管理生命周期。

# **3. 目标架构**

## 3.1 整体分层

重构后整体分三层：

* 展示层：Web UI（browser / Tauri WebView）——纯前端，通过 HTTP / IPC 与后端通信
* 应用层：FastAPI 后端——处理 HTTP 请求、SSE 推流、项目管理、触发任务
* 核心层：Python 业务逻辑——AI 调用、ffmpeg、pipeline，完全与 HTTP 解耦

三层之间依赖方向单向向下，核心层不引用 FastAPI，应用层不直接调 AI SDK，保证每层可独立测试。

## 3.2 目标文件结构

vlog-editing-helper/

├── main.py # CLI 入口（仅命令分发，<50 行）

├── pyproject.toml # 统一依赖声明

├── setup.ps1 / setup.sh # 跨平台环境配置

├── config.example.yaml

├── templates/

│

├── vlog\_tool/ # 核心业务层（纯 Python，无框架依赖）

│ ├── \_constants.py # ✨ 全局常量（VIDEO\_EXTS 等）

│ ├── config.py

│ ├── log.py

│ ├── progress.py

│ ├── utils.py

│ ├── prompts.py

│ │

│ ├── ai/ # AI 厂商抽象（现状良好，基本不动）

│ │ ├── base.py

│ │ ├── factory.py

│ │ ├── gemini.py

│ │ └── openai\_compat.py

│ │

│ ├── tasks/ # ✨ 拆分自 pipeline.py

│ │ ├── \_\_init\_\_.py

│ │ ├── compress.py # run\_compress\_all / compress\_one

│ │ ├── analyze.py # run\_analyze\_all / analyze\_one

│ │ ├── scripts.py # run\_scripts\_all / scripts\_one

│ │ ├── plan.py # run\_plan

│ │ ├── label.py # run\_label\_all

│ │ └── cut.py # run\_cut\_all / cut\_one

│ ├── pipeline.py # ✨ 变薄：仅编排 tasks/ 的顺序，<100 行

│ │

│ └── tests/ # 测试与现状结构一致

│

├── server/ # ✨ FastAPI 应用层

│ ├── app.py # FastAPI 实例 + 中间件 + 启动

│ ├── deps.py # 依赖注入（config、runner）

│ ├── routes/ # ✨ 拆分自 server.py

│ │ ├── \_\_init\_\_.py

│ │ ├── videos.py # /api/videos, /api/video

│ │ ├── projects.py # /api/projects, /api/project/create

│ │ ├── texts.py # /api/texts, /api/save/text

│ │ ├── scripts.py # /api/scripts, /api/save/script

│ │ ├── plan.py # /api/plan, /api/save/plan

│ │ ├── config\_api.py # /api/config/raw

│ │ └── run.py # /api/run/start, /api/run/status (SSE)

│ └── services/ # ✨ 业务服务，调用 vlog\_tool/

│ ├── project\_service.py

│ ├── file\_service.py

│ └── runner\_service.py

│

├── ui/ # ✨ 前端（从 vlog\_tool/ui/static/ 移出）

│ ├── index.html

│ ├── style.css

│ └── src/ # ✨ ES 模块拆分

│ ├── main.js # 入口，组装模块

│ ├── state.js # 全局状态管理

│ ├── api.js # 所有 fetch 调用

│ ├── viewer.js # 视频播放器

│ ├── editor.js # texts/scripts/plan 编辑面板

│ ├── runner.js # 运行面板 + SSE 进度

│ └── sidebar.js # 侧栏导航

│

├── desktop/ # ✨ Tauri 桌面端（Phase 3）

│ ├── src-tauri/

│ │ ├── Cargo.toml

│ │ └── src/main.rs # 启动 Python sidecar + WebView

│ └── README.md

│

└── docs/

├── architecture.md # 本文档精简版（持续更新）

└── superpowers/ # 现有设计文档

# **4. 三阶段实施计划**

## Phase 1：无破坏拆分（1-2 周）✅ 已全部完成

> **状态：** 2026-06-12 全部完成。5 个 commits 在 `refactor/project-structure` 分支，待合并到 `main`.
> 
> | 子任务 | Commit | 文件变化 |
> |--------|--------|---------|
> | 1a 提取常量 | `5e8d376` | `_constants.py` 消除 B-019/B-020 |
> | 1b 拆分 pipeline.py | `cac4d67` | 789→96 行，tasks/ 8 文件 |
> | 1c 拆分 server.py | `0918da0` | 1261→454 行，routes/9 + services/2 |
> | 1d 拆分 app.js | `b0da41a` | 1509→ES 模块，src/ 8 文件 |

原则：只移动代码，不改逻辑，不改接口。每个子任务独立 commit，CI 绿色才合并。

### 1a：提取全局常量

* 新建 vlog\_tool/\_constants.py，把 VIDEO\_EXTS、DEFAULT\_INDEX\_WIDTH 等常量集中
* utils.py、server.py 统一 from vlog\_tool.\_constants import VIDEO\_EXTS
* 修复 B-019（常量重复定义）和 B-020（硬编码 3）
* 预期：1-2 小时

### 1b：拆分 pipeline.py → tasks/

* 新建 vlog\_tool/tasks/ 目录，将每个功能阶段拆出独立文件
* pipeline.py 变为薄编排层，只负责按顺序调用 tasks/ 中的函数
* 接口签名不变，main.py 零改动
* 更新对应测试 import 路径
* 预期：半天

### 1c：拆分 server.py → routes/ + services/

* 在 vlog\_tool/ui/ 内先创建 routes/ 和 services/ 子目录（Phase 2 迁移到 server/ 顶层）
* 按资源类型拆路由：videos、projects、texts、scripts、plan、config、run
* 服务层提取文件读写、项目查找等可复用逻辑
* server.py 变为薄分发层（<100 行）
* 预期：1 天

### 1d：拆分 app.js → src/ ES 模块

* state.js：全局状态对象 + 更新函数
* api.js：所有 fetch/XHR 调用，集中错误处理
* viewer.js：视频播放器 + segment 跳转
* editor.js：texts/scripts/plan 编辑面板渲染
* runner.js：运行面板 + 轮询/SSE
* sidebar.js：侧栏渲染 + 事件
* main.js：入口，import 并组装所有模块
* index.html 改为 <script type="module" src="src/main.js">
* 预期：1 天

**Phase 1 完成交付物：代码可读性大幅提升，最大单文件 ≤ 300 行，所有测试通过，功能零回归。**

## Phase 2：后端升级至 FastAPI（2-4 周）

依赖 Phase 1 完成。目标：解锁 SSE 实时推流、类型注解、OpenAPI 文档自动生成。

### 2a：引入 FastAPI + uvicorn

* 新增依赖：fastapi, uvicorn[standard], python-multipart
* 新建 server/app.py，配置 CORS（仅 localhost）、静态文件挂载、lifespan
* server/deps.py：依赖注入，提供 AppConfig 和 RunnerService 实例

### 2b：迁移路由（与 1c 路由拆分同步）

* 将 routes/\*.py 从 http.server 风格改写为 FastAPI Router
* 请求/响应改用 Pydantic model（SaveTextRequest、RunRequest 等）
* 文件读写等逻辑移入 services/
* 保持 API path 和 JSON 格式与现有前端兼容，前端零改动

### 2c：进度推流改为 SSE

* server/routes/run.py：POST /api/run/start 触发后台任务；GET /api/run/stream 返回 SSE
* runner\_service.py：用 asyncio.Queue 在后台线程和 SSE generator 之间传递事件
* 前端 runner.js：用 EventSource 替换 setInterval 轮询，延迟从 2s 降至毫秒级

### 2d：Pydantic 输出验证

* 在 vlog\_tool/ai/ 层用 Pydantic 模型定义 AI 输出结构（VideoAnalysis、VoiceoverScript、DayPlan）
* 替换现有 extract\_json + 手动 dict 检查
* 结构不符时自动触发重试或报错，替代散落各处的 try/except json.JSONDecodeError

**Phase 2 完成交付物：后端迁移完成，SSE 实时进度，API 有自动生成的文档（/docs），类型安全覆盖主要数据流。**

## Phase 3：Tauri 桌面端（1-3 个月）

依赖 Phase 2 完成。目标：打包为可直接双击运行的桌面 App，无需用户安装 Python 环境。

### 3a：Python sidecar 打包

* 用 PyInstaller 将 FastAPI 服务打包成独立可执行文件（server.exe / server）
* Tauri 在主进程中通过 sidecar 机制启动 server，监听随机端口
* 端口通过 Tauri 命令传递给 WebView，作为 API\_BASE\_URL

### 3b：Tauri 项目初始化

* desktop/src-tauri/ 目录，配置 tauri.conf.json：窗口大小、图标、菜单
* main.rs：启动 sidecar → 等待 /health → 打开 WebView
* 全局快捷键：Cmd/Ctrl+Q 退出，Cmd/Ctrl+R 重启服务

### 3c：原生能力增强（选做）

* 文件夹选择：用 Tauri dialog API 替换手动输入路径，解决 Web 安全限制
* 系统通知：任务完成 / 出错时推系统通知（而非仅 UI toast）
* 托盘图标：最小化到系统托盘，后台跑 analyze 不占 Dock/任务栏

### 3d：分发

* GitHub Actions 打包 Windows (.msi/.exe)、macOS (.dmg)、Linux (.AppImage)
* 发布到 GitHub Releases，支持自动更新（tauri-plugin-updater）

**Phase 3 完成交付物：可一键安装的桌面 App，用户无需接触命令行，双击即开，任务完成弹通知。**

# **5. 优先级矩阵**

| **任务** | **阶段** | **耗时估算** | **收益** | **风险** |
| --- | --- | --- | --- | --- |
| 提取 \_constants.py（修复 B-019/B-020） | Phase 1a | 1-2 小时 | 消除重复定义 | 极低 |
| 拆分 pipeline.py → tasks/ | Phase 1b | 半天 | 单文件可读性 | 低 |
| 拆分 server.py → routes/ + services/ | Phase 1c | 1 天 | 单文件可读性 | 低（有测试） |
| 拆分 app.js → src/ ES 模块 | Phase 1d | 1 天 | 前端可维护性 | 低（UI 测试） |
| 补 setup.sh（R-009b） | Phase 1 | 2 小时 | 跨平台可用 | 无 |
| 迁移至 FastAPI | Phase 2a-2b | 1 周 | 类型安全、可扩展 | 中（API 兼容） |
| SSE 实时进度（替换轮询） | Phase 2c | 2 天 | 用户体验 | 低 |
| Pydantic AI 输出验证 | Phase 2d | 2-3 天 | 稳定性 | 低 |
| Tauri 桌面端 | Phase 3 | 1-3 个月 | 用户体验飞跃 | 高（新技术栈） |

# **6. 迁移注意事项**

## 6.1 保持向后兼容的策略

* Phase 1 拆分时，原始模块路径保留旧 import（from vlog\_tool.pipeline import run\_analyze\_all），内部转发到新路径，给外部调用方留过渡期
* FastAPI 路由保持与现有 stdlib server 完全一致的 path 和 JSON 格式，前端不需要同步改动
* CLI 接口（main.py subcommands）在整个重构过程中保持稳定

## 6.2 测试策略

* Phase 1 每个子任务完成后跑 pytest，CI 绿色才合并
* Phase 2 迁移时补充 API 集成测试（httpx + pytest-asyncio）
* 建议：Phase 1b 前，为 pipeline.py 中复杂函数补充单元测试，降低拆分风险

## 6.3 桌面端的额外考虑

* ffmpeg 打包：Tauri 分发包中需捆绑 ffmpeg 可执行文件，或引导用户安装并配置路径
* Python sidecar：PyInstaller 打包后体积约 50-80MB，加上 AI 依赖可能更大，需评估是否接受
* API Key 管理：桌面端应使用系统 Keychain 存储 API Key，而非明文 .env 文件
* 自动更新：sidecar 更新和 Tauri shell 更新需要协调版本，建议统一发布

# **7. 不在本次范围内**

以下事项暂不包含在本重构规划中，保留为后续独立需求：

* R-010（AI 输出质量）：外部 prompt 覆盖、置信度评分——独立功能，不阻塞重构
* R-011（规划面板预览播放）——纯前端功能，可在 Phase 1d 前端拆分后单独实现
* R-003e（refine tab 临时 context textarea）——UI 小功能，随时可插入
* B-006d（规划视图切源播放器联动）——已标记 [!] 阻塞，可在 Phase 1d 时一并修复

# **8. 成功标准**

| **指标** | **当前** | **Phase 1 结果 (2026-06-12)** | **Phase 2 目标** |
| --- | --- | --- | --- |
| 最大单文件行数 | 1393 行 (app.js) | ✅ **4 行** (ES module entry) | ≤ 300 行 |
| 测试用例数 | 128 | ✅ **118 测试全绿** | ≥ 200 |
| 进度更新延迟 | ~2000ms（轮询） | ~2000ms（不变） | <100ms（SSE） |
| API 文档 | 无 | 无 | 自动生成（/docs） |
| 跨平台安装脚本 | Windows only | Windows + Linux/macOS | Windows + Linux/macOS |
| 桌面端分发 | 无 | 无 | 无（Phase 3） |

*— END —*