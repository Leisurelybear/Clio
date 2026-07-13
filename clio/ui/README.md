# 可视化编辑 UI

本地 web 工具，在浏览器里看视频、读 AI 输出、就地修改保存。

## 启动

```bash
.\.venv\Scripts\python.exe main.py serve
# 默认 http://127.0.0.1:8765/ ，自动打开浏览器
```

常用参数：

```bash
python main.py serve --port 9000        # 换端口
python main.py serve --no-browser       # 不开浏览器（远程机调试）
python main.py serve --host 0.0.0.0     # 暴露到局域网（注意安全）
```

按 `Ctrl+C` 退出。

## 界面布局

侧栏分两段：**项目**（跨视频的产物）放上面，**视频**（per-video 产物）放下面。
点 sidebar 的项目条目会切换右栏内容；点视频条目会切换右栏 + 播放器。
⚙ 设置也是项目级入口：点开后右侧渲染完整 config 编辑表单。
▶ 运行：支持多步骤流水线（压缩→分析→口播→vlog 剪辑规划→标号），实时进度 + ETA。
日志和统计也是项目级入口：日志面板实时读取服务日志，统计面板汇总 AI token 用量。

```
┌────────────────────────────────────────────┐
│ 项目: E:\Videos\Franch2 [压缩|原视频] [重新加载] │
├──────────┬──────────────────┬──────────────┤
│ 项目      │  视频播放器       │  视频模式    │
│ 编排  1   │  ▶ 00:00 / 00:42 │ ┌ 分析 ┐     │
│ 设置  2   │                  │ │ 摘要 │     │
│ 运行  3   │                  │ │ 时间轴│     │
│ 日志  4   │                  │ └──────┘     │
│ 统计  5   │                  │ ┌ 口播 ┐     │
│ ────────  │                  │ ┌ 转录 ┐     │
│ 视频      │                  │   [保存]     │
│ [001]xxx  │                  │              │
│ [002]yyy  │                  │              │
└──────────┴──────────────────┴──────────────┘
```

点 📋 规划时，tab 栏隐藏，右栏整块渲染规划面板 + 保存按钮；播放器保持上一个视频：

```
┌──────────┬──────────────────┬──────────────┐
│ 📋 规划 ●│  视频播放器       │  规划模式    │
│ ⚙ 设置   │  (上一个视频)     │ ┌ 主题 ──┐    │
│ ▶ 运行   │                  │ │        │    │
│          │                  │ └────────┘    │
│ 视频      │                  │ ┌ 顺序 ──┐    │
│ [001]xxx  │                  │ │ seg 1  │    │
│ [002]yyy  │                  │ │ seg 2  │    │
│          │                  │ └────────┘    │
│          │                  │   [保存]     │
└──────────┴──────────────────┴──────────────┘
```

点 ⚙ 设置时，右栏渲染完整 config 嵌套表单（paths / ai / compress / analyze / script / plan 等全部字段），每个配置分区包裹在可折叠的卡片中，左侧带 accent 色条标识层级。
- 编辑**全局 config.yaml**（全局 tab）：保存后需重启服务生效。
- 编辑**项目 project.yaml**（项目 tab）：保存后立即生效。
- 编辑**项目专属 project.yaml**（通过 `?project=X` 切换）：保存后立即生效，下次流水线运行自动加载新配置。
校验失败（如 provider 拼写错误）时弹出错误红字，不写文件。

Provider registry also has focused backend endpoints for integrations and future UI refactors:

- `GET /api/providers` returns global `ai.providers`.
- `POST /api/providers` creates a provider from a JSON body containing `name`, `type`, `api_key_env`, `base_url`, `models`, and `capabilities`.
- `PUT /api/providers/{name}` creates or updates one provider.
- `DELETE /api/providers/{name}` removes one provider from global `config.yaml`.

These endpoints require the same API token as other sensitive config routes and invalidate the server config cache after writes.

## 数据来源

UI 只读 / 写 `config.yaml` 里 `paths.output_dir` 下的文件：

| 入口 | 路径 | 文件 | 字段 |
| --- | --- | --- | --- |
| 分析 (texts) | sidebar → 视频 → tab「分析」 | `output/texts*/*.json` | `title`, `location`, `mood`, `summary`, `timeline[]`，可含同期声 `transcript` |
| 口播 (scripts) | sidebar → 视频 → tab「口播」 | `output/scripts/*_voiceover.json` | `title`, `voiceover`, `edit_tip`, `duration_hint_sec` |
| 转录 (transcript) | sidebar → 视频 → tab「转录」 | `output/transcripts/*.json` | `segments[]`，支持手动添加、编辑、删除 |
| 规划 (plan) | sidebar → 📋 规划 | `output/plans/day<N>_plan.json` | `theme`, `opening_tip`, `ending_tip`, `sequence[]` |
| 设置 (config) | sidebar → ⚙ 设置 → 项目 tab | `project.yaml` | 项目级字段，嵌套表单渲染 |
| 设置 (config) | sidebar → ⚙ 设置 → 全局 tab | `config.yaml`（global-only 字段） | 保存后需重启服务 |
| 设置 (config) | sidebar → ⚙ 设置 → 合并视图 tab | 合并后配置 | 只读查看全局+项目字段来源 |
| 日志 (logs) | sidebar → 日志 | `logs/YYYY-MM-DD-HH.log` | 服务运行日志，支持自动刷新 |
| 统计 (tokens) | sidebar → 统计 | `output/token_usage.json` | 总 token、按模型、按任务、最近 100 条历史 |
| 多项目 | sidebar 顶部选择器 / URL `?project=name` | 自动发现 `project.json` | 支持新建、打开、切换 |

`texts*` 通配同时匹配 `texts/` 和 `texts - 巴黎/` 之类的目录。

## 视频源切换 (Source Toggle)

header 右侧的 **`压缩` / `原视频`** 切换按钮决定侧栏列的是哪一边：

- **压缩**：列 `output/compressed/` 下的 640p 视频（默认）。适合看 AI 标注的时间码在压缩版上对不对。
- **原视频**：列项目 `videos.json` 中选中的 4K 原始素材（可来自任意磁盘路径）。适合看真实细节 / 选镜头。

每个视频条目都带一个 match 角标，标出对应的另一边文件名：

```
[001] GL010695  → 压: 001_GL010695.mp4     ← 压缩视图，对应原视频
[002] GL010741  → 压: 002_GL010741.mp4
```
```
[001] GL010695.MP4  → 原: GL010695.MP4      ← 原视频视图，对应压缩版
[002] GL010741.MP4  → 原: GL010741.MP4
```

**匹配规则**（大小写不敏感）：

- 压缩 → 原：剥掉 `001_` 之类的前缀，在 `videos.json` / `.vmeta.source_path` 里找同 stem 的文件
- 原 → 压：在 `output/compressed/` 里找 `*_<原 stem>.mp4`（必须带 `_<index>_` 前缀）

**边角情况**：

- 某一边没找到对应 → 角标显示 `无对应` 且整行变暗；点进去 `texts` / `口播` tab 会显示"没有对应 JSON"
- 在 `texts` / `口播` tab 有未保存改动时切换源 → 弹确认框，避免丢改动
- `规划 (plan)` tab 不受源影响，按 `sequence[].index` 在当前视图里找对应视频并跳转
- **在规划视图（sidebar 📋 规划 激活）下点 header 的源切换**：仅刷新视频列表 + 清空播放器，**不会**把视图切回视频模式（规划 vs 视频是两个独立工作区）。要回到视频模式，点 sidebar 的某个视频条目即可

## 规划预览播放

在播放器下方有规划预览条；进入「编排」后，可用播放/上一段/下一段按钮按 `sequence[]` 连续预览：

- 每个 segment 按 `use_timeline` 的开始时间跳转，播到结束时间后自动推进到下一个
- 当前播放的 segment 会在规划列表和预览条里高亮
- 预览条显示已播 / 当前 / 待播段，点击某段可跳转
- 再次点击播放按钮可停止；播完所有 segment 后自动停止
- 切换到视频 / 运行 / 设置 tab 或切换源时自动停止预览

## 播放速度

播放器下方的时间栏右侧有速度选择器，支持：
`0.5x` / `0.75x` / `1x` / `1.25x` / `1.5x` / `2x`

预览播放时也可调整速度，适合快速浏览编排效果。

## 快捷键

- `Ctrl+S` — 保存当前 tab 的修改
- `Ctrl+1` ~ `Ctrl+5` — 切换项目区入口：编排 / 设置 / 运行 / 日志 / 统计
- `Ctrl+B` — 折叠 / 展开左侧栏
- `Ctrl+\` — 折叠 / 展开右侧编辑栏
- `Escape` — 关闭打开中的 modal；编辑转录文本时结束编辑
- 点 timeline / plan 的 segment — 视频跳到对应时间

## 安全

- 默认仅监听 `127.0.0.1`，不暴露到局域网
- 使用 `--host 0.0.0.0` 暴露到局域网时，服务会自动生成访问 token；终端会打印带 `?token=` 的 Token URL，前端也会把 token 写入 `Authorization: Bearer ...`
- 也可以通过 `--token <value>` 显式指定 token；远程访问时不要把 token URL 发给不可信设备
- 目录浏览接口 `/api/fs/dirs` 只允许访问用户主目录内的路径；Windows 下仅额外允许列出驱动器根目录
- 所有文件 IO 沙盒在 `output_dir` 内：basename 不允许 `/` `\` `..`
- 写入采用 atomic rename (写 `.tmp` 然后 `os.replace`)，不会留下半截文件
- 首次覆盖某个文件时自动创建 `*.bak` 备份（已存在则不覆盖）

## 故障排查

| 现象 | 排查 |
| --- | --- |
| 启动报 `Address already in use` | 换端口：`--port 9000`，或杀掉占用进程 |
| 切到原视频视图后列表全空 | 项目尚无 `videos.json` 或列表为空。点击侧栏「添加视频」勾选素材，或对旧项目运行 `python main.py migrate` |
| 浏览器打开空白 | 看终端输出 + `logs/YYYY-MM-DD-HH.log` |
| `texts` tab 一直说"没有 JSON" | 视频列表里该行 `texts` 状态是 `·` 灰色；说明 `output/texts*` 下没匹配文件 |
| 保存后 clip 看到旧内容 | 按浏览器 `Ctrl+Shift+R` 强刷；服务器 `/api/videos` 走的是缓存头 `no-store`，但浏览器可能缓了 JSON |
| 设置 tab 显示"配置数据不可用" | 当前项目没有 `project.yaml` 且全局 `config.yaml` 读取失败；检查 config.yaml 是否存在并格式正确 |
| 切换项目后 AI 行为没变 | 检查项目目录下是否有 `project.yaml`；没有则使用全局 config.yaml 的 AI 配置 |

## Prompt Management

Settings includes a `Prompts` sub-tab for editing AI prompt templates from the browser.

- The list shows every built-in prompt and whether the current project has an override.
- Saving writes a project-level file under `<project_dir>/templates/prompts/{PROMPT_NAME}.md`.
- Restore deletes project-level overrides for that prompt; repo-level overrides, if present, still apply.
- The next AI call uses the updated prompt automatically.

## Run Panel Input Directory

The Run panel has a per-run input directory field with a browse button.

- The value is sent only with the current run request and does not modify `project.yaml`.
- If no files are selected in the sidebar, the selected steps process all videos in that directory.
- If sidebar file selection is active, only the selected filenames are passed to the run request.

After a run finishes while the Run panel is still open, the UI switches to the most relevant result view:

- `plan` opens the generated plan for the selected day.
- `voiceover`, `transcribe`, and `analyze` open the compressed video detail view on the matching tab.
- `compress` and `label` open the compressed video list.
