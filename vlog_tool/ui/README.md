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

```
┌────────────────────────────────────────────┐
│ 项目: E:\Videos\Franch2    [重新加载]      │
├──────────┬──────────────────┬──────────────┤
│ 视频列表 │  视频播放器       │  Tab 切换    │
│          │  ▶ 00:00 / 00:42 │ ┌──分析─┐    │
│ [001]xxx │                  │ │ 摘要  │    │
│ [002]yyy │                  │ │ 时间轴│    │
│          │                  │ └────────┘    │
│          │                  │ ┌──口播─┐    │
│          │                  │ │ 文案  │    │
│          │                  │ └────────┘    │
│          │                  │ ┌──规划─┐    │
│          │                  │ │ seq[] │    │
│          │                  │ └────────┘    │
└──────────┴──────────────────┴──────────────┘
```

## 数据来源

UI 只读 / 写 `config.yaml` 里 `paths.output_dir` 下的文件：

| Tab | 文件 | 字段 |
| --- | --- | --- |
| 分析 (texts) | `output/texts*/*.json` | `title`, `location`, `mood`, `summary`, `timeline[]` |
| 口播 (scripts) | `output/scripts/*_voiceover.json` | `title`, `voiceover`, `edit_tip`, `duration_hint_sec` |
| 规划 (plan) | `output/plans/day<N>_plan.json` | `theme`, `opening_tip`, `ending_tip`, `sequence[]` |

`texts*` 通配同时匹配 `texts/` 和 `texts - 巴黎/` 之类的目录。

## 快捷键

- `Ctrl+S` — 保存当前 tab 的修改
- 点 timeline / plan 的 segment — 视频跳到对应时间

## 安全

- 默认仅监听 `127.0.0.1`，不暴露到局域网
- 所有文件 IO 沙盒在 `output_dir` 内：basename 不允许 `/` `\` `..`
- 写入采用 atomic rename (写 `.tmp` 然后 `os.replace`)，不会留下半截文件
- 首次覆盖某个文件时自动创建 `*.bak` 备份（已存在则不覆盖）

## 故障排查

| 现象 | 排查 |
| --- | --- |
| 启动报 `Address already in use` | 换端口：`--port 9000`，或杀掉占用进程 |
| 浏览器打开空白 | 看终端输出 + `logs/YYYY-MM-DD-HH.log` |
| `texts` tab 一直说"没有 JSON" | 视频列表里该行 `texts` 状态是 `·` 灰色；说明 `output/texts*` 下没匹配文件 |
| 保存后 clip 看到旧内容 | 按浏览器 `Ctrl+Shift+R` 强刷；服务器 `/api/videos` 走的是缓存头 `no-store`，但浏览器可能缓了 JSON |
