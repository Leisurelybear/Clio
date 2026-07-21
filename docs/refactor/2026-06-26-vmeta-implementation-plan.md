# `.vmeta` / `.vindex` 实施报告

> 实施完成报告，记录实际实现与规划的差异。

## 背景

**要解决的核心问题**：压缩完成后没有持久化原始视频路径和分段关系，导致后续步骤每次都要重新推断，且有多处推断逻辑有 bug。

**两个新文件的分工**：

| 文件 | 命名 | 方向 | 数量 |
|------|------|------|------|
| `001_GL010683.vmeta` | 与压缩文件同名 | 压缩 → 原始 | 每个压缩文件 1 个 |
| `GL010683.vindex` | 原始文件 stem | 原始 → 全部压缩 | 每个原始文件 1 个 |

**降级原则**：所有读取处均保留原有逻辑作为 fallback，存量项目无需任何迁移操作。

## 实施结果：11 个 Commit

```
cd795df feat(vmeta): add .vmeta/.vindex sidecar module with 13 tests
329e70e feat(compress): write .vmeta/.vindex after compression
2d9fe24 fix(analyze): use .vindex in single_file mode to find all segments
94a1926 perf(csv): avoid ffprobe in _write_csv by reading .vmeta first
373a611 fix(cut): read .vmeta in _resolve_video_path and _compute_segment_offset
79384d5 feat(reindex): add reindex command + UI /api/vmeta endpoint
b4fd911  fix(cut,vmeta): use glob instead of hardcoded .mp4 extension
73f8132 refactor(compress): put split temp files in compressed_dir
720e827 fix(ui): _find_original_for_compressed reads .vmeta first; _find_compressed_for_original reads .vindex first
e879996 fix(routes): videos.py segment offset reads .vmeta.split_info.offset_sec; run.py passes comp_dir
73bdb11 refactor(ui): remove Stage 2 sibling auto-discovery from _list_projects
```

## 与规划的关键差异

### 1. `split.py` 修改（规划中遗漏）

规划假设 `split_manifest.json` 在 `compressed_dir`，但实际 `split.py` 写到了 `splits_dir`。
解决方案：向 `split_video()` 新增 `manifest_dir: Path | None = None` 参数，在 `compress.py` 调用时传入 `manifest_dir=config.compressed_dir`。

### 2. `VideoMeta.read` 的 JSON 结构解析修复

规划的 `VideoMeta.read` 从顶层 `raw.get("split_info")` 读取，但实际上 `split_info` 嵌套在 `raw["data"]` 内。
实现修正：`data = raw.get("data", raw); si = data.get("split_info")`，兼容新旧两种 JSON 结构。

### 3. 测试覆盖面增加

| 项目 | 规划 | 实际 |
|------|------|------|
| `test_vmeta.py` | 12 个 | 13 个（增加 `test_vindex_is_split_false_for_single`）|
| `test_helpers.py` | 2 个 | 3 个（增加 `test_uses_disk_meta_when_record_has_no_meta`）|
| `test_tasks_analyze.py` | 1 个 | 1 个 |
| `test_tasks_cut.py` | 2 个 | 2 个 |
| **合计** | **17 个** | **19 个** |

### 4. 代码审查发现的修复

实现完成后审查发现两个 `硬编码 .mp4` bug，在第 7 个 commit 修复：

- `_compute_segment_offset(cut.py)`：使用 `comp_dir.glob(f"{compressed_stem}.*")` 代替 `comp_dir / f"{compressed_stem}.mp4"`
- `handle_get_vmeta(videos.py)`：使用 `comp_dir.glob(f"{stem}.*")` + `VIDEO_EXTS` 过滤代替 `f"{stem}.mp4"`

### 6. 合并 split 临时文件到 compressed_dir（Commit 8）

规划中 split 临时文件写入 `splits_subdir`，但所有消费者都已按数字前缀过滤（`prefix.isdigit()`），因此 split 临时文件（无数字前缀，如 `GL010684_seg01.mp4`）可以安全地与压缩文件共存于 `compressed_dir`。

改动：`compress.py` 将 `split_video` 的输出目录从 `output_dir/splits` 改为 `config.compressed_dir`。

### 5. `_write_vindex` 不处理 skip_existing 分支

当 `skip_existing=True` 且压缩文件已存在时，`run_compress_all` 的跳过分支创建的 `ClipRecord` 不含 `meta` 字段。
`_write_vindex` 过滤 `rec.meta is None` 的记录，因此 skip 场景不会写 `.vindex`。

**结论**：用户首次集成后需运行 `python main.py reindex` 为新系统补全 `.vindex` 文件。
这已作为独立子命令提供，不影响存量项目。

## 代码审查结论

### ✅ 向后兼容

所有消费者均具备完整降级链：

| 消费者 | 降级路径 |
|--------|----------|
| `analyze.py:single_file` | `.vindex` → stem 匹配（修复只取 [0] bug）|
| `cut.py:_compute_segment_offset` | `.vmeta.split_info` → 时长比例估算 |
| `cut.py:_resolve_video_path` | `.vmeta.source_path` → rglob 递归匹配 |
| `_helpers.py:_get_video_info` | `rec.meta` → `VideoMeta.read()` → `probe_video_info` |
| `reindex.py` | `.vmeta` → stem 反解 |

### ✅ 异常安全

- 损坏的 `.vmeta`/`.vindex`：`except Exception: return None`，不抛异常
- 文件路径变更（重新挂载）：`src.is_file()` 检查，失败则降级
- ffprobe 失败：`_safe_duration` 返回 `0.0`，不中断流程

### ⚠️ 注意事项

1. **reindex 后 `.vmeta` 缺少 `split_info`**：重建 `.vmeta` 时 `reindex.py` 没有存储 `split_info`（因为原始 manifest 可能已不存在）。`is_split_segment=False`，`split_info=None`。这不会影响功能，`_compute_segment_offset` 会降级到估算。

2. **`.vindex` 只在实际压缩后写入**：skip_existing 场景不会触发 `_write_vindex`。用户需主动 `reindex`。

## 改动文件总览

| 文件 | 改动性质 |
|------|----------|
| `vlog_tool/vmeta.py` | 新建 |
| `vlog_tool/tests/test_vmeta.py` | 新建 |
| `vlog_tool/split.py` | 新增 `manifest_dir` 参数 |
| `vlog_tool/tasks/_helpers.py` | `ClipRecord` 增 `meta` 字段 + `_get_video_info` 函数 |
| `vlog_tool/tasks/compress.py` | 写入 `.vmeta`/`.vindex` |
| `vlog_tool/tasks/analyze.py` | `single_file` 分支优先读 `.vindex` |
| `vlog_tool/tasks/cut.py` | 两个函数优先读 `.vmeta` + 修复 B-06 |
| `vlog_tool/tasks/reindex.py` | 新建 |
| `main.py` | 新增 `reindex` 子命令 |
| `vlog_tool/ui/routes/videos.py` | 新增 `handle_get_vmeta` |
| `vlog_tool/ui/server.py` | 注册 `/api/vmeta/` 路由 |

---

*实施完成 · 2026-06-26 · 分支: feat/vmeta-sidecar*
