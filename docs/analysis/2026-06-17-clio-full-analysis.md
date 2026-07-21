# vlog-editing-helper 全面问题分析报告

> **目标**：做一个完善的 AI 剪辑软件，开箱即用  
> **分析范围**：全部 Python 源码 + JS 前端 + 配置体系（6054 行 Python，2014 行 JS）  
> **分析日期**：2026-06-17

---

## 一、执行摘要

项目整体架构清晰，核心断点续跑机制完善，测试覆盖率高，是一个有相当工程质量的个人工具。距离"开箱即用的 AI 剪辑软件"还有以下几个核心差距：

| 类别 | 问题数 | 最高优先级 |
|------|--------|----------|
| 🔴 可用性（用户直接感知） | 5 | 无法取消任务、ffmpeg 进程泄漏 |
| 🟡 性能（影响效率） | 3 | 全串行、无并发、OpenAI 调用无 max_tokens |
| 🟠 健壮性（偶发但影响体验） | 7 | AI 返回无校验、文件写入非原子、refine 写文件非原子 |
| 🔵 体验（与"开箱即用"的差距） | 8 | Windows 锁定、无安装包、配置门槛高等 |
| ⚪ 代码质量（维护性） | 6 | closure 陷阱、全局缓存非进程隔离、prompt 硬编码等 |

---

## 二、🔴 可用性问题（用户直接感知，必须修复）

### P0-1：无法取消正在运行的 Pipeline

**位置**：`clio/ui/routes/run.py` → `handle_post_run_start()`，`clio/ui/static/src/runner.js`

**现象**：Web UI 点击"运行"后，`_run_thread` 是一个 daemon Thread，但没有任何取消机制。用户在 UI 上无法停止正在运行的任务。前端的"运行中..."按钮变为 disabled，但没有取消按钮。

**影响**：压缩一个 1 小时的 GoPro 原片可能需要 5-15 分钟，期间用户无法干预。如果配错了参数或选错了视频，只能强制关闭浏览器或杀掉 Python 进程。

**根因**：
```python
# run.py
handler._run_thread = threading.Thread(target=_run, daemon=True)
handler._run_thread.start()
# 没有 cancel_event，没有 stop 接口
```

**修复方案**：
```python
# 1. 在 Handler 类上增加 cancel event（class-level）
_cancel_event = threading.Event()

# 2. 每个 task for 循环开头检查
for i, item in enumerate(items):
    if cancel_event and cancel_event.is_set():
        print("[取消] pipeline 被用户终止")
        break

# 3. run_ffmpeg 中增加 cancel 支持
def run_ffmpeg(args, ffmpeg, progress_callback=None, cancel_event=None):
    process = subprocess.Popen(cmd, ...)
    try:
        for line in process.stderr or []:
            if cancel_event and cancel_event.is_set():
                process.terminate()
                raise InterruptedError("ffmpeg 被取消")
            ...
    except BaseException:
        process.terminate()
        process.wait()
        raise

# 4. 新增 POST /api/run/cancel 接口
def handle_post_run_cancel(handler, qs, obj):
    handler.__class__._cancel_event.set()
    handler._send_json({"ok": True, "message": "cancel requested"})

# 5. 前端 runner.js 增加取消按钮
```

---

### P0-2：ffmpeg 子进程在意外中断时泄漏

**位置**：`clio/utils.py` → `run_ffmpeg()`，`clio/tasks/transcribe.py` → `_extract_audio()`

**现象**：Ctrl+C、kill 进程、或 Web UI 关闭浏览器后，已启动的 ffmpeg 子进程不会被 kill，持续占用 CPU 和磁盘 I/O。

**根因**：
```python
# utils.py
process = subprocess.Popen(cmd, ...)
for line in process.stderr or []:  # 如果这里被中断
    ...
process.wait()  # 永远不会执行到
# ffmpeg 在后台无限运行
```

`_extract_audio()` 有 `try/finally` 删除临时 wav 文件，但没有 terminate ffmpeg。

**修复方案**：
```python
def run_ffmpeg(args, ffmpeg, progress_callback=None, cancel_event=None):
    cmd = [ffmpeg, *args]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        for line in process.stderr or []:
            if cancel_event and cancel_event.is_set():
                process.terminate()
                raise InterruptedError("ffmpeg 被取消")
            print(line, end="")
            if progress_callback:
                m = time_pat.search(line)
                if m:
                    progress_callback(...)
        process.wait()
        if process.returncode != 0:
            raise RuntimeError(...)
    except BaseException:
        # 确保在任何异常（含 Ctrl+C）时都终止子进程
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        raise
```

---

### P0-3：scripts 步骤写文件非原子，中断会产生损坏 JSON

**位置**：`clio/tasks/scripts.py` → `run_generate_scripts()`

**现象**：写 voiceover JSON 和 MD 使用的是 `out.write_text(...)`，非原子。AI 调用返回后、写入完成前发生中断（Ctrl+C、OOM、磁盘满），会产生空文件或不完整 JSON。下次运行时 `skip_existing` 会判断文件已存在并跳过，导致永久遗漏这条输出。

**根因**：
```python
# scripts.py
out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")  # 非原子！
md_out.write_text(...)  # 同样非原子
```

其他步骤（analyze、plan）均使用了 `write_json_atomic()`，scripts 是遗漏。

**修复**：
```python
from vlog_tool.utils import write_json_atomic, write_text_atomic

write_json_atomic(out, script)

md_content = (f"# {script.get('title', json_file.stem)} 口播\n\n"
              f"{script.get('voiceover', '')}\n\n"
              f"**剪辑建议**: {script.get('edit_tip', '')}\n")
write_text_atomic(md_out, md_content)
```

同样的问题也存在于 `run_refine_texts()` 和 `run_refine_scripts()`：
```python
# refine.py
json_file.write_text(json.dumps(refined, ...), encoding="utf-8")  # 非原子！
txt_path.write_text(...)  # 非原子！
```

---

### P0-4：label 步骤视频文件写入无保护，损坏后被跳过

**位置**：`clio/tasks/label.py` → `run_label_videos()`

**现象**：ffmpeg 烧录序号的视频文件直接写到输出目标路径，无原子保护。中断后产生不完整的 mp4 文件，下次运行 `skip_existing` 看到文件存在就跳过，用户拿到的是损坏视频。

**根因**：
```python
run_ffmpeg(["-i", str(compressed), "-vf", vf, "-an", "-y", str(out)], ffmpeg)
# 直接写到 out，没有 tmp + rename
```

视频文件无法用 `os.replace()` 做原子写入（文件可能很大），但可以用"写临时文件 + 检验完整性再 rename"的方案：
```python
tmp_out = out.with_suffix(f".tmp.{os.urandom(4).hex()}.mp4")
try:
    run_ffmpeg(["-i", str(compressed), "-vf", vf, "-an", "-y", str(tmp_out)], ffmpeg)
    # ffmpeg 正常退出 = 文件完整
    tmp_out.replace(out)
except Exception:
    tmp_out.unlink(missing_ok=True)
    raise
```

同样的问题存在于 `compress_video()` 和 `cut_one()`，ffmpeg 直接写目标文件。

---

### P0-5：plan 步骤不记录 ProcessingState，UI 状态矩阵永远显示空

**位置**：`clio/tasks/plan.py` → `run_plan_vlog()`

**现象**：UI 状态矩阵表格中，plan 列对所有文件永远显示空，用户无法判断 plan 是否已完成。

**根因**：`run_plan_vlog()` 没有调用 `state.mark()`，是遗漏。

**修复**（两行）：
```python
state = ProcessingState(config.paths.output_dir)
# ... 生成 plan 后 ...
for clip in clips:
    source_stem = clip.get("source_stem", "")
    if source_stem:
        state.mark(source_stem, "plan", "done")
```

---

## 三、🟡 性能问题（影响效率）

### P1-1：全串行处理，20 个视频顺序调 Gemini API

**位置**：`clio/tasks/analyze.py` → `run_analyze_all()`，`clio/tasks/scripts.py` → `run_generate_scripts()`

**现象**：每个视频串行上传 → 等待 Gemini 处理（通常 10-30s）→ 分析。20 个视频约需 400-600 秒（6-10 分钟），全部是 I/O 等待时间。

**根因**：简单 for 循环，没有任何并发。

**影响**：最耗时的步骤没有任何优化，严重影响"开箱即用"体验。

**修复方案（ThreadPoolExecutor，最小改动）**：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_analyze_all(config, tracker=None, single_file=None):
    ...
    MAX_WORKERS = min(3, len(items))  # 默认 3 并发，可从 config 读
    
    def _analyze_one(compressed, original, idx_str, position):
        # 原有的单文件分析逻辑，封装为函数
        ...
        return ClipRecord(...)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_analyze_one, c, o, i, pos): (c, o, i)
            for pos, (c, o, i) in enumerate(items, 1)
        }
        for fut in as_completed(futures):
            record = fut.result()  # 异常在此抛出
            if tracker:
                tracker.next(message=f"完成 {record.stem}")
            records.append(record)
```

ProgressTracker 已有 `threading.Lock` 保护，ProcessingState 也是线程安全的。

**预估收益**：20 个视频从 ~500s → ~180s（3 并发）。

---

### P1-2：OpenAI 兼容 API 调用没有 max_tokens，可能被截断或超时

**位置**：`clio/ai/openai_compat.py` → `generate_text()`

**现象**：调用 DeepSeek/通义等 API 时，请求体中没有 `max_tokens` 参数。部分 API 默认值很低（如某些版本的 DeepSeek 默认 1024 tokens），口播文案或 plan 可能被静默截断，导致 JSON 不完整，下游 `extract_json()` 报错。

**根因**：
```python
json={
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    # 没有 max_tokens！
}
```

**修复**：
```python
json={
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "max_tokens": 4096,  # 足够覆盖所有输出，可从 config 配置
    "temperature": 0.3,  # 减少随机性，提高 JSON 格式稳定性
}
```

---

### P1-3：Web UI 用轮询（2s 间隔），无法实时感知完成

**位置**：`clio/ui/static/src/runner.js` → `pollRunStatus()`，`setInterval(pollRunStatus, 2000)`

**现象**：pipeline 完成后，UI 最多需要 2 秒才能更新。更严重的是：如果用户切换了 tab，`$('run-progress')` 找不到元素，轮询默默失败（`if (!prog) return`），状态永远不更新。

**根因**：`http.server` 不支持 SSE（Server-Sent Events），强制使用轮询方案。

**中期修复（不换框架）**：把轮询间隔降至 500ms，并修复 tab 切换时的 DOM 失效问题：
```javascript
// 不依赖 DOM 元素存在，状态存到 state.runStatus
async function pollRunStatus() {
    try {
        const s = await api('GET', '/api/run/status');
        state.runStatus = s;
        _renderRunStatus();  // 根据当前是否在 run tab 决定是否渲染
        if (s.status === 'done' || s.status === 'error') _stopRunPoll();
    } catch { ... }
}
```

**长期修复（迁移 FastAPI + SSE）**：见第五章。

---

## 四、🟠 健壮性问题（偶发但影响体验）

### P2-1：AI 返回无结构化校验，字段缺失在下游才暴露

**位置**：`clio/analyze.py` → `analyze_video()` / `generate_voiceover()` / `plan_daily_vlog()`

**现象**：`extract_json(text)` 只做 JSON 解析。AI 偶尔返回缺少 `timeline`、`title`、`sequence` 等字段时（尤其是 Gemini 思考过长、响应被截断时），错误在下游才出现（`KeyError`、`AttributeError`、CSV 写入空值），定位困难。

**根因**：没有在 AI 调用返回后立即做结构验证。

**修复**：引入轻量校验（不需要 Pydantic，用 dataclass 或简单 dict 检查即可）：

```python
def _validate_analysis(data: dict, source: str) -> dict:
    """校验 AI 分析结果，缺失字段补默认值并告警。"""
    required = {"title", "summary", "timeline"}
    missing = required - data.keys()
    if missing:
        print(f"  [警告] {source}: AI 返回缺少字段 {missing}，使用默认值")
    data.setdefault("title", Path(source).stem)
    data.setdefault("summary", "")
    data.setdefault("timeline", [])
    data.setdefault("highlights", [])
    data.setdefault("location", "未知")
    data.setdefault("mood", "")
    data.setdefault("suggested_use", "")
    return data

# analyze_video() 返回时：
return _validate_analysis(extract_json(text), video_path)
```

对 voiceover 和 plan 做同样处理。

---

### P2-2：split 分片写 manifest，但失败时 manifest 不存在导致 compress 重复分片

**位置**：`clio/split.py` → `split_video()`

**现象**：长视频分片后写 `{stem}_split_manifest.json`，但如果分片中途失败（磁盘满、ffmpeg 报错），已写的分片不会清理，manifest 不存在。下次运行时，`run_compress_all()` 的分片跳过逻辑依赖 `orig_to_compressed` 查找，可能因部分分片存在而跳过，也可能因 manifest 缺失而重新分片，行为不确定。

**修复**：用原子写入 + 失败时清理：
```python
segments_written = []
try:
    for i in range(num):
        ...
        run_ffmpeg(args, ffmpeg)
        segments_written.append(seg_path)
    # 全部成功再写 manifest
    manifest_path.write_text(json.dumps(manifest, ...), encoding="utf-8")
    return segments
except Exception:
    # 清理已写的分片文件
    for f in segments_written:
        f.unlink(missing_ok=True)
    raise
```

---

### P2-3：`_trip_context_cache` 进程级全局缓存，Web UI 多项目切换时读到旧值

**位置**：`clio/analyze.py` → `_trip_context_cache`，`_read_trip_context()`

**现象**：缓存 key 是 `input_dir` 字符串，Web UI 在同一进程中切换项目时，若两个项目共享同一 `input_dir`（或 `templates/trip_context.md` 内容变化），仍会读到旧缓存。

**修复**：把 `context_file` 的 mtime 也纳入缓存 key：
```python
def _read_trip_context(project_dir: str) -> str:
    path = Path(project_dir) / "templates" / "trip_context.md"
    if not path.is_file():
        return ""
    mtime = path.stat().st_mtime
    key = f"{project_dir}@{mtime}"
    if key in _trip_context_cache:
        return _trip_context_cache[key]
    text = path.read_text(encoding="utf-8").strip()
    _trip_context_cache[key] = text
    return text
```

---

### P2-4：`_provider_cache` 进程级全局，config 热更新后仍使用旧 provider

**位置**：`clio/ai/factory.py` → `_provider_cache`

**现象**：Web UI 更新 config（`PUT /api/config/raw`）后，会提示"需要重启服务"，但如果用户不重启，`_provider_cache` 里仍然是旧 API Key / 旧 base_url 的 provider 实例，调用会继续使用旧配置。

**修复**：在 `config_routes.py` 保存配置后调用 `_clear_provider_cache()`：
```python
# config_routes.py
from vlog_tool.ai.factory import _clear_provider_cache

def handle_put_config_raw(handler, qs, obj):
    # ... 保存 config ...
    _clear_provider_cache()  # 强制下次调用重新构建 provider
    handler._send_json({"ok": True, "message": "配置已保存，无需重启即可生效"})
```

这样 AI Key 更新后立即生效，不需要重启。

---

### P2-5：`run_transcribe_all()` 用 `input_dir` 扫描原始视频，忽略 `recursive` 配置

**位置**：`clio/tasks/transcribe.py` → `run_transcribe_all()`

**现象**：
```python
for f in sorted(config.paths.input_dir.iterdir()):  # 只扫一层！
    if f.is_file() and f.suffix.lower() in VIDEO_EXTS:
        stems.add(f.stem)
```

其他步骤（compress）使用 `find_videos(input_dir, recursive=config.paths.recursive)` 支持子目录扫描，transcribe 步骤没有遵循同一约定，导致子目录视频不被转录。

**修复**：
```python
from vlog_tool.utils import find_videos
videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
stems = sorted(set(v.stem for v in videos))
```

---

### P2-6：`run_analyze_all()` 中 `existing` 验证逻辑存在 edge case

**位置**：`clio/tasks/analyze.py`

**现象**：
```python
existing = sorted(config.texts_dir.glob(f"{idx_str}_*.json"))
if config.analyze.skip_existing and existing:
    candidate = existing[0]
    try:
        existing_data = json.loads(candidate.read_text(...))
        if existing_data.get("source_file", "") == original.name:
            json_path = candidate
```

如果 `existing[0]` 是一个有效 JSON 但 `source_file` 字段不匹配（例如同一 index 但不同原始文件），会跳过验证，继续重新分析并尝试写一个**同名**的文件。由于 `_build_stem()` 用 AI 返回的 title 生成文件名，若新 title 与旧文件名不同，旧文件会遗留在目录中。

**修复**：增加对旧文件的清理或告警：
```python
if existing_data.get("source_file", "") != original.name:
    print(f"  [覆盖] {candidate.name} 的 source_file 不匹配，将重新分析")
    candidate.unlink()  # 清理旧文件
    candidate.with_suffix(".txt").unlink(missing_ok=True)
```

---

### P2-7：compress 步骤 MIN_VALID_SIZE=256 判断太宽松

**位置**：`clio/tasks/compress.py`

**现象**：
```python
MIN_VALID_SIZE = 256
if f.stat().st_size < MIN_VALID_SIZE:
    continue
```

一个损坏但 > 256 bytes 的压缩文件（例如 ffmpeg 刚写了文件头就崩了，实际可能有几 KB）会被认为是有效的并跳过重新压缩。用户拿到的是无法播放的视频。

**修复**：用 ffprobe 做基本完整性检查，或至少提高阈值（完整的 640p mp4 文件至少几十 KB）：
```python
MIN_VALID_SIZE = 50 * 1024  # 50KB，比合理的最小压缩视频更小但足以过滤损坏头
```

---

## 五、🔵 体验问题（与"开箱即用"目标的差距）

### UX-1：强制绑定 Windows，无法在 macOS/Linux 运行

**位置**：`setup.ps1`（PowerShell 专用），README 中所有路径示例

**现象**：
- 唯一的安装脚本是 `setup.ps1`（PowerShell）
- README 示例全是 Windows 路径：`E:/Videos/云南`、`.\setup.ps1`、`.\venv\Scripts\Activate.ps1`
- `main.py check` 中虚拟环境检测只认 Windows `Scripts/` 目录：
  ```python
  Path(sys.executable).parent.name.lower() == "scripts"  # Linux 是 bin/
  ```
- ROADMAP 中 `setup.sh` 被标注为"低优先级"

**影响**：macOS 用户（大量 GoPro 用户使用 Mac）、Linux 用户完全无法使用安装引导，需要手动操作。

**修复**：
```bash
# setup.sh
#!/bin/bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# brew install ffmpeg (macOS) / apt install ffmpeg (Ubuntu)
```

同时修复 `main.py check` 的虚拟环境检测：
```python
venv_name = Path(sys.executable).parent.name.lower()
in_venv = venv_name in ("scripts", "bin") or ".venv" in sys.executable or "venv" in sys.executable
```

---

### UX-2：配置门槛极高，新用户上手成本大

**现象**：
1. 用户必须手动编辑 YAML 文件才能填写 API Key
2. `config.yaml` 有 50+ 个配置项，新用户不知道最少需要填哪几个
3. 首次运行没有配置引导（wizard），直接报错 `AI 任务配置不完整`
4. Web UI 的设置页面存在但没有验证反馈——填了错误的 API Key 也不提示

**修复**：
- Web UI 首次打开时，检测到 `config.yaml` 不存在或 API Key 为空，弹出"初始配置向导"（3 步：填 API Key → 选输入目录 → 测试连接）
- `python main.py check` 的输出已经很好，考虑在 `serve` 启动时自动运行 check，若失败则在 Web UI 首页显示警告横幅

---

### UX-3：Whisper 转录功能体验残缺

**位置**：`clio/whisper_cli.py`，`clio/tasks/transcribe.py`

**现象**：
- Whisper 需要单独 `pip install -r requirements-whisper.txt`，但 Web UI 的 Whisper 检测接口（`GET /api/whisper/check`）只检查是否安装，不提供安装引导
- 首次使用 Whisper medium 模型需要下载约 1.5GB 模型文件，下载时没有进度显示，用户以为程序卡死
- `whisper.enabled: false` 默认关闭，但 UI 的运行面板仍然显示"Whisper 语音转录"步骤并可勾选，勾选后直接跳过并显示"已跳过"，体验混乱

**修复**：
- 下载模型时显示进度：`faster_whisper` 底层用 HuggingFace Hub 下载，可以配置 `HUGGINGFACE_HUB_VERBOSITY=info`
- UI 的 Whisper 步骤在 `whisper.enabled=false` 时应该灰显并显示"未启用（在设置中开启）"

---

### UX-4：label 步骤依赖 texts 目录而非 compressed 目录，行为反直觉

**位置**：`clio/tasks/label.py`

**现象**：`run_label_videos()` 通过遍历 `config.texts_dir.glob("*.json")` 来找视频，这意味着：
- 如果 analyze 没跑，label 步骤什么都不做
- 新加入的视频（已压缩但未分析）不会被标注
- 用户期望"烧录序号"是对所有压缩视频操作，实际只对已分析的视频操作

**修复**：改为遍历 `compressed_dir`：
```python
files = sorted(config.compressed_dir.glob("*.mp4"))
for compressed in files:
    idx = compressed.stem.split("_", 1)[0]
    out = labeled_dir / f"{compressed.stem}_labeled.mp4"
    ...
```

---

### UX-5：错误信息对用户不友好

**现象**：
- Gemini API 429 报错：打印 `Gemini API 不可重试错误: ...`，用户不知道是 quota 问题还是 Key 无效
- `FileNotFoundError: 找不到 ffmpeg` 发生在第一个视频开始处理时，不是在启动时
- `AI 分析全部失败（N 个失败）` 的错误信息没有给出具体原因，用户不知道是网络还是 Key

**修复**：在 `main.py check` 和 Web UI 启动时做前置检查，将错误细化：
```python
# Gemini 429 特别处理
if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
    print("  [错误] Gemini API 配额用尽。请等待配额重置（通常 1 分钟），"
          "或在 config.yaml 设置 requests_per_minute 限速。")
```

---

### UX-6：plan 步骤只支持单日，多日 vlog 需要多次手动执行

**位置**：`clio/tasks/plan.py`，`main.py` → `plan` 子命令

**现象**：每次运行 plan 只能生成一个 day 的规划（`--day day1`）。多天旅行的 vlog 需要手动执行：
```bash
python main.py plan --day day1
python main.py plan --day day2
python main.py plan --day day3
```

没有自动按日期/文件夹分组素材的功能，也没有批量生成多天规划的命令。

**修复**：增加 `plan --all-days` 参数，自动按 `day1, day2, ...` 批量生成。

---

### UX-7：cut 步骤和 CapCut/剪映导出功能未完成

**位置**：`ROADMAP.md`，`clio/tasks/cut.py`

**现象**：`cut` 命令存在于 ROADMAP 但在 Web UI 中没有入口（R-008 全部未完成）。更重要的是，ROADMAP 中提到的"剪映草稿导出格式"（CapCut JSON）完全没有实现。这是"开箱即用"目标中最关键的最后一步——把规划结果直接导入剪映，而不是让用户手动对照。

**这是距离"开箱即用"最大的功能缺口。**

---

### UX-8：Web UI 的 Runner 在运行中途切换 Tab 会丢失进度更新

**位置**：`clio/ui/static/src/runner.js`

**现象**：用户在 pipeline 运行中切换到 texts/voiceover tab，再切换回来，进度面板仍然显示最后一次渲染的状态（不是实时更新的），因为 `_runPollTimer` 仍在运行但 DOM 元素不存在时 `pollRunStatus()` 会 `return` 而不渲染。

**修复**：把进度状态存到 `state.runStatus`，切换回 run tab 时触发一次渲染：
```javascript
// state.js
state.runStatus = null;

// runner.js pollRunStatus
state.runStatus = s;
if ($('run-progress')) _renderRunStatus(s);  // 当前在 run tab 时才渲染

// 切换到 run tab 时
export function renderRun() {
    ...
    if (state.runStatus) _renderRunStatus(state.runStatus);  // 恢复上次状态
}
```

---

## 六、⚪ 代码质量问题（影响维护性）

### Q-1：ANALYZE_PROMPT 硬编码 `旅行 vlog`，不适合其他 vlog 类型

**位置**：`clio/prompts.py`

```python
ANALYZE_PROMPT = """请分析这段旅行 vlog 原始素材视频..."""
```

prompt 中多处提到"旅行"（`旅行 vlog 口播文案写手`、`旅行 vlog 剪辑策划`），导致工具实际上只适合旅行类 vlog。如果用于美食、日常、运动等内容，AI 会按旅行框架输出不匹配的分析。

ROADMAP R-010 已计划"外部 prompt 文件覆盖机制"，但优先级较低。建议：
- 将 prompt 移到 `templates/prompts/` 目录（已在 ROADMAP R-010a 计划）
- `config.yaml` 增加 `ai.vlog_type: travel|food|daily|sport` 参数，自动选择对应 prompt

---

### Q-2：compress 循环中 closure 陷阱

**位置**：`clio/tasks/compress.py`

```python
for i, (original, source) in enumerate(items, start=1):
    ...
    def _on_progress(_sec: float, total_dur: float):
        pct = int(_sec / total_dur * 100) if total_dur > 0 else 0
        tracker.update(
            phase="compress", current=i, ...  # i 是 late binding，当前串行没问题
        )
    compress_video(source, use_out, config, progress_callback=_on_progress)
```

当前串行执行不触发，但若后续并发化，`i` 会是循环末尾值（Python 闭包 late binding）。

**修复**：使用默认参数绑定：
```python
def _make_progress(i, name):
    def _cb(_sec, total_dur, _i=i, _name=name):
        pct = int(_sec / total_dur * 100) if total_dur > 0 else 0
        tracker.update(phase="compress", current=_i, message=f"压缩 {_name} ({pct}%)")
    return _cb
compress_video(source, use_out, config, progress_callback=_make_progress(i, source.name))
```

---

### Q-3：`_provider_cache` 是全局 module-level 变量，测试之间互相污染

**位置**：`clio/ai/factory.py`

```python
_provider_cache: dict[tuple, TextAIProvider] = {}  # 进程级全局
```

测试中 mock 了一个 provider，但如果之前的测试已经把真实（或其他 mock）provider 写入了 cache，当前测试会用到旧的 cached provider。`_clear_provider_cache()` 存在但测试的 `conftest.py` 没有自动调用它。

**修复**：在 `conftest.py` 加 autouse fixture：
```python
@pytest.fixture(autouse=True)
def clear_provider_cache():
    from vlog_tool.ai.factory import _clear_provider_cache
    _clear_provider_cache()
    yield
    _clear_provider_cache()
```

---

### Q-4：`compress_video()` 中音频码率预留计算使用魔法数字

**位置**：`clio/compress.py`

```python
target_bits -= int(128_000 * duration * 1.05)  # 预留 128kbps 音频 + 5% 余量
```

当 `remove_audio=True`（默认值）时这段代码会跳过，但如果用户配置 `remove_audio: false`，这个 128kbps 的假设可能与实际音频码率差异较大（AAC 通常 96-256kbps）。更合理的做法是用 ffprobe 探测音频流的实际码率。

---

### Q-5：`run_ffmpeg()` 把 ffmpeg 的 stderr 全部 print 到控制台

**位置**：`clio/utils.py`

```python
for line in process.stderr or []:
    print(line, end="")  # ffmpeg 每帧都输出一行，极其嘈杂
```

ffmpeg 压缩时每帧都输出进度信息，导致控制台/日志文件被大量刷屏。同时日志文件（`_HourlyFileHandler`）也会记录所有这些行，日志文件会迅速膨胀。

**修复**：只打印关键错误行和最终统计：
```python
for line in process.stderr or []:
    # 只保留进度回调，不打印每行
    if progress_callback:
        m = time_pat.search(line)
        if m:
            ...
    elif "error" in line.lower() or "warning" in line.lower():
        print(line, end="")  # 只打印 error/warning
```

---

### Q-6：`TRANSCRIPT_CONTEXT` prompt 使用英文

**位置**：`clio/prompts.py`

```python
TRANSCRIPT_CONTEXT = """
Additionally, here are the spoken content (transcript) segments...
"""
```

所有其他 prompt 都是中文，唯独 `TRANSCRIPT_CONTEXT` 是英文，风格不统一，且与中文前缀拼接后语言混乱，可能影响 AI 的输出质量（AI 可能开始用英文回复）。

**修复**：改为中文：
```python
TRANSCRIPT_CONTEXT = """
以下是各素材的语音转录片段，请结合口播内容优化剪辑顺序和时间安排：

{transcripts_json}
"""
```

---

## 七、路线图建议（针对"开箱即用"目标）

按优先级排序：

### 阶段一：稳定性（2 周）

| 优先级 | 任务 | 预估工作量 |
|--------|------|----------|
| P0 | 增加 Cancel 机制（threading.Event + ffmpeg terminate） | 1 天 |
| P0 | ffmpeg 写视频文件改 tmp+rename（compress/label/cut） | 0.5 天 |
| P0 | scripts/refine 写文件改 write_json_atomic | 0.5 天 |
| P0 | OpenAI API 调用加 max_tokens + temperature | 0.5 天 |
| P0 | AI 返回加结构校验（缺失字段补默认值并告警） | 1 天 |

### 阶段二：性能与体验（2 周）

| 优先级 | 任务 | 预估工作量 |
|--------|------|----------|
| P1 | analyze/scripts 并发化（ThreadPoolExecutor，max_workers=3） | 2 天 |
| P1 | 添加 setup.sh（macOS/Linux 支持） | 0.5 天 |
| P1 | 修复 transcribe 的 recursive 扫描和状态记录 | 0.5 天 |
| P1 | plan 步骤补全 ProcessingState 记录 | 0.5 天 |
| P1 | Web UI 首次配置向导（API Key 填写 + 测试连接） | 2 天 |

### 阶段三：核心功能完善（4 周）

| 优先级 | 任务 | 预估工作量 |
|--------|------|----------|
| P2 | 实现 CapCut/剪映草稿 JSON 导出（最高价值功能） | 1 周 |
| P2 | Web UI 支持 cut 步骤（R-008 完成） | 1 周 |
| P2 | prompt 外部化（templates/prompts/），支持非旅行类型 vlog | 3 天 |
| P2 | provider cache 热更新（config 保存后无需重启） | 1 天 |
| P2 | 多天 plan 批量生成（`plan --all-days`） | 1 天 |

---

## 附：项目现有亮点（值得保留）

以下设计质量较高，在修改时请保留：

1. **原子写入** (`write_json_atomic`)：已覆盖 JSON 和文本，是数据安全的核心
2. **ProcessingState 状态矩阵**：文件级 × 步骤级持久化，断点续跑的基础
3. **指数退避重试** (`with_retry`)：正确处理 Gemini 429 / ServerError
4. **`ai.context` 注入机制**：行程背景前置到所有 prompt，有效减少 AI 误判
5. **多 AI 厂商抽象**：任务与 provider 完全解耦，切换零代码改动
6. **refine + fix 模式**：定向修正功能设计精良，用户体验独特
7. **分片视频 (split) 的 manifest**：提供了可追溯的分片记录
8. **`python main.py check`**：环境检查 CLI 体验很好，覆盖全面

---

*本报告基于全量源码静态分析，覆盖所有 Python 文件（6054 行）和 JavaScript 前端（2014 行）。*
