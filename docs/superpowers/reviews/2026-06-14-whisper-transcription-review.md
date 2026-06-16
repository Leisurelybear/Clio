# Review: Whisper ASR 转录集成 — 设计文档

> 2026-06-14 · reviewer: AI assistant
> 源文档: `docs/superpowers/specs/2026-06-14-whisper-transcription-design.md`

---

## 总评

设计扎实、结构清晰、考虑周全。架构决策合理（独立 pipeline step 不经过 AI provider 层），时间轴映射正确（`offset_sec` 与现有逻辑一致），向后兼容设计到位（`transcripts_map` 可空、默认关闭）。建议小幅修订后进入实现阶段。

---

## 主要问题

### 1. 音频提取参数未明确

§4/§5 未写出 ffmpeg 命令。§5 写"直接 demux 极快"有误导——faster-whisper 需要 16kHz 单声道 WAV，这是**重采样**而非简单 demux。

**建议**：明确写出命令行并修正描述：
```
ffmpeg -i <input> -vn -acodec pcm_s16le -ar 16000 -ac 1 <output.wav>
```

### 2. `_resolve_original()` 无去重

`run_transcribe_all` 扫描 `compressed/` 后对每个文件调 `_resolve_original()`。同一原始视频如果有 split 段 + 完整压缩版，会触发多次转录同一个原始文件。

**建议**：改为扫描 → 去重拿到 `original_stem` 集合 → 对每个 unique stem 只转录一次。

### 3. 路由名不规范

§8.4 用 `/api/transcript`（单数），现有路由均为复数：`/api/videos`、`/api/projects`、`/api/config`。

**建议**：统一为 `/api/transcripts`（复数）。

### 4. `requirements-whisper.txt` 依赖碎片化

设计说不加入 `requirements.txt` / `requirements-locked.txt`，但 faster-whisper 依赖 `ctranslate2`、`onnxruntime`、`torch` 等重量级包。用户安装基础依赖后还得额外装 Whisper，体验碎片化。

**建议**：在 `requirements-whisper.txt` 中 lock 版本，同时在 `requirements.txt` 中注释掉引用行，用户自行取消注释。

### 5. 缺少 `language: auto` 选项

当前枚举为 `zh | en`，但多语言混用的 vlog 场景需要自动检测。

**建议**：枚举扩展为 `zh | en | auto`，`auto` 时向 `model.transcribe()` 传 `language=None`。

---

## 次要问题

| 位置 | 问题 | 建议 |
|------|------|------|
| §3 | `WhisperConfig` 的 `sanitize` 归属未指明 | 明确是独立方法还是集成到 `ConfigSanitizer` |
| §5 step 4 | 临时文件清理方式未定 | 参考 B-003 教训，使用 `tempfile.NamedTemporaryFile(delete=True)` 或 `try/finally` |
| §5 step 5 | `transcripts_summary.csv` 用途未说明 | 删掉（YAGNI）或写明消费者 |
| §8.1 | UI 用 `🎤` emoji 做角标 | 实现时建议用 CSS class（`.has-transcript`）或纯文本角标 "(T)"，因 AGENTS.md 约定免 emoji |
| §8.2 | compress 生成的 .lrv 可能无音轨 | 文档补充注明：无音轨的视频自动跳过转录 |
| §9 | `.gitignore` 追加 `models/` | 正确，与 `compressed/`、`output/` 风格一致 |
| §10 | mock `subprocess.run` 需适配 Windows | 注意与 `compress.py` 中的 ffmpeg 调用风格保持一致 |
| §1 | "远期 option" 应明确未排期 | 注明不在 Phase 1 范围内，避免 scope creep |
| §6 | `max_segments_per_clip` 的 clip 粒度过小时可返回空 | 文档应说明：空列表时该 clip 无 transcript 注入，向后兼容已确保 |

---

## 合理/正确的设计决策

- 独立 pipeline step，不走 AI provider 层 — Whisper 是非生成式任务，正确
- 单例模型缓存 + `cache_key` — `model_size`/`cache_dir` 变化时重载，正确
- `transcripts_map` 可空 → Plan prompt 跳过注入，向后兼容
- `whisper.enabled: false` 默认关闭，优雅降级
- 测试全 mock `WhisperModel` 不跑真实模型，符合项目 pytest 风格
- Files Changed Checklist 完整覆盖所有层，便于实现

---

*— END —*
