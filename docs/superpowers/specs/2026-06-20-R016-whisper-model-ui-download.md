# R-016: UI 化 Whisper 模型下载

## 背景

当前 faster-whisper 模型下载只有 CLI 入口（`python main.py whisper install`）。
中国用户必须配置 `hf_endpoint` 镜像源，下载失败时 UI 只显示"未安装"或
"模型加载失败"，没有引导用户下载的操作入口。

## 验收标准

1. [ ] 后端 `POST /api/whisper/install` — 在 daemon 线程中下载模型，进度写入 `.whisper_install.json`
2. [ ] 后端 `GET /api/whisper/install/status` — 轮询下载进度（百分比 / 速度 / 状态）
3. [ ] 前端转录错误区显示"下载模型"按钮（当模型未缓存或 whisper 未安装时）
4. [ ] 按钮点击后触发下载，UI 显示实时进度（下载速度 / 百分比 / 剩余时间）
5. [ ] 下载完成后自动重试当前视频的转录
6. [ ] 后端复用 `whisper_cli.run_whisper_install` 的预下载逻辑

## 设计

### 后端 API

#### `POST /api/whisper/install`
- 请求体: `{}`
- 行为: 启动 daemon 线程，复用 `whisper_cli.run_whisper_install` 的下载逻辑
- 进度写入 `output_dir/.whisper_install.json`
- 响应: `{ "ok": true }`

#### `GET /api/whisper/install/status`
- 响应:
```json
{
  "status": "downloading|done|error|idle",
  "progress_pct": 45,
  "message": "正在下载 model.bin (45%)",
  "speed": "12.5 MB/s",
  "eta_sec": 120
}
```

### 进度文件 `.whisper_install.json`
```json
{
  "status": "downloading",
  "progress_pct": 45,
  "message": "正在下载 model.bin...",
  "speed": "12.5 MB/s",
  "eta_sec": 120
}
```

### 前端交互

**转录 tab** (`editor.js:renderTranscript`):
- 当前: 无转录数据时显示纯文本提示
- 改为: 先调用 `GET /api/whisper/check` 检测 whisper 安装状态
- 若 whisper 未安装 → 显示"安装 faster-whisper 依赖"按钮 + "下载模型"按钮
- 若 whisper 已安装但模型未缓存 → 显示"下载模型"按钮
- 点击后显示进度条 + 下载速度 + 取消按钮
- 完成后自动调用当前视频的 rerun transcribe

**runner.js**:
- 转录步骤运行前，若 whisper 未安装或模型未缓存，自动触发下载
- 下载期间显示进度，完成后继续流水线

### 实现步骤

1. **R-016a**: 后端 `POST /api/whisper/install` + `GET /api/whisper/install/status`
   - 新增 `whisper_routes.py` 中的 `handle_post_whisper_install`
   - 复用 `whisper_cli._snapshot_download` 的 huggingface_hub 下载
   - 使用 `huggingface_hub.hf_hub_download` 替代 `snapshot_download`（支持回调）
2. **R-016b**: 前端转录 error 区显示下载按钮 + 进度
3. **R-016c**: 下载完成后自动 rerun transcribe

### 关键实现细节

- huggingface_hub 的 `hf_hub_download` 支持 `callback` 参数，可获取下载进度
- 使用 `whisper_cli.run_whisper_install` 的 pip install 部分安装依赖
- 下载线程使用 daemon=True，不阻塞 UI
- 下载进度写入 `.whisper_install.json`，前端 1s 轮询
- 下载完成后删除 `.whisper_install.json`

### 风险

- huggingface_hub 可能未安装：先 pip install huggingface_hub
- 下载中断：支持 resume（`resume_download=True`）
- 磁盘空间不足：下载前检查 `disk_usage`
