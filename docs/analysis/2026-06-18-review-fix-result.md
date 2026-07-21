# 2026-06-18 审查修复结果

> 基于 `2026-06-18-clio-review.md` 的修复记录。

## 已修改文件（7 files, +65/-12 lines）

| 文件 | 改动 | 原因 |
|------|------|------|
| `clio/tasks/cut.py` | +13/-4 | P0-1: 改用 `write_json_atomic`/`write_text_atomic`；R-4: 添加 `cancel_event` 支持 |
| `clio/ui/server.py` | +3/-1 | P0-2: project.json 迁移改用 `write_json_atomic` |
| `clio/tasks/plan.py` | +1/-1 | P0-4: transcript 加载条件追加 `config.plan.use_transcripts` |
| `clio/compress.py` | +30/-2 | R-2: 用 `_get_audio_bitrate()` (ffprobe) 替代 128kbps 魔数 |
| `clio/tasks/analyze.py` | +22/-2 | R-3: `run_analyze_all` 启动时一次性 `_build_stem_to_path` 缓存，避免每次 rglob 全目录扫描 |
| `clio/cut.py` | +4/-1 | R-4: `cut_one` 添加 `cancel_event` 参数并传给 `run_ffmpeg` |
| `clio/pipeline.py` | +1/-1 | Q-2: `run_pipeline_steps` 增加 `"cut"` 到 cancel_event 传递列表 |

## 已确认无需修改项

| 问题 | 原因 |
|------|------|
| P0-3 (conftest provider cache 污染) | **已存在** `_clear_ai_cache` autouse fixture |
| R-1 (AI 返回缺结构校验) | **已存在** `_validate_analysis` / `_validate_voiceover` / `_validate_plan` |
| Q-1 (compress closure 陷阱) | **已修复** — 默认参数绑定 `_i: int = i` |

## Review 结论

### 各改动正确性

1. **cut.py 原子写入** ✓ — `write_json_atomic` 写入 JSON (tmp+rename)，`write_text_atomic` 写入 manifest.md；参数匹配原有行为
2. **server.py 原子写入** ✓ — `write_json_atomic(project_path, cur)` 替换 `project_path.write_text(json.dumps(...))`；仍在原有 `try/except` 内，异常安全
3. **plan.py use_transcripts** ✓ — 条件追加后，`config.plan.use_transcripts=False` 时不加载 transcript，`transcripts_map` 保持为空
4. **compress.py 音频码率探测** ✓ — ffprobe 探测第一音频流码率，失败时回退 128kbps；仅 `not cfg.remove_audio` 时调用
5. **analyze.py rglob 缓存** ✓ — `_build_stem_to_path` 一次性递归扫描构建 `{stem_lower: path}` 映射；`_resolve_original` 新增可选 `stem_cache` 参数，提供时走 O(1) 查找，否则保留原磁盘扫描行为
6. **cut_one cancel_event** ✓ — 参数默认 `None`，向前兼容；传给 `run_ffmpeg`
7. **pipeline cancel_event** ✓ — 增加 `"cut"`；当前 pipeline 不含 cut 步骤，属前瞻性改动

### 无引入新问题

- 420/420 测试通过
- Ruff lint 无警告
- 所有函数签名向后兼容（新增参数均有默认值 `None`/`False`）
- 原子写入使用现有 `utils.py` 的 `try/unlink` 保障，崩溃安全

### 未实现的低优先级项

- **Perf-1**: AI 分析并发化 (ThreadPoolExecutor) — 涉及线程安全和速率控制，需单独规划设计
- **Perf-2**: ProcessingState 批量 flush — 当前串行场景非瓶颈
