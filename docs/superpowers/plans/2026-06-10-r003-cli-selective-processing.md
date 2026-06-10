# R-003 CLI Selective Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `compress`/`analyze`/`scripts` CLI subcommands to accept a single file (not just directory) via `-i`, and add `--context` to `refine` for temporary context override.

**Architecture:** Three changes to `main.py` dispatch + three pipeline functions + context_override thread through analyze.py. No config dataclass changes.

**Tech Stack:** Python 3.11+, argparse, Pathlib

---

### Task 1: `pipeline.py` — Add `_next_index()` helper

**Modify:** `vlog_tool/pipeline.py` (after the `_build_stem` function)

- [ ] **Step 1: Add `_next_index` helper**

```python
def _next_index(scan_dir: Path, index_width: int = 3) -> int:
    """Scan scan_dir for {index}_* prefixed files and return next available index."""
    if not scan_dir.is_dir():
        return 1
    max_idx = 0
    for p in scan_dir.iterdir():
        stem = p.stem
        if "_" in stem:
            prefix = stem.split("_", 1)[0]
            if prefix.isdigit():
                idx = int(prefix)
                if idx > max_idx:
                    max_idx = idx
    return max_idx + 1
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `.venv/Scripts/python.exe -m pytest vlog_tool/tests/ -v`
Expected: 118 passed

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/pipeline.py
git commit -m "feat(pipeline): add _next_index helper for single-file index assignment"
```

---

### Task 2: `main.py` — File detection + `--context` arg

**Modify:** `G:\Coding_Project\IdeaProjects\vlog-video-analysis\main.py`

- [ ] **Step 1: Add `--context` / `-C` arg to refine parser**

After line 185 (`--fix` arg), add:

```python
    p_refine.add_argument(
        "--context", "-C",
        type=str,
        default="",
        help="临时上下文说明，附加到 ai.context 之后（仅本次 refine 生效）",
    )
```

- [ ] **Step 2: Refactor dispatch — detect single-file before `_prepare_config`**

The current dispatch at lines 192-266 calls `_prepare_config` which passes `args.input` to `apply_run_paths`. We need to intercept single-file before that.

Replace lines 192-266 (from `args = parser.parse_args(argv)` through the entire dispatch block) with:

```python
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}", file=sys.stderr)
        return 1

    base_config = load_config(config_path)
    setup_logging(base_config.paths.logs_dir)

    if args.command == "check":
        return run_check(config_path, getattr(args, "input", None))

    # ── Single-file detection ────────────────────────────────────────
    # If -i points to a single file, don't let _prepare_config set it as input_dir
    single_file: Path | None = None
    raw_input = getattr(args, "input", None)
    if raw_input is not None and raw_input.is_file():
        single_file = raw_input
        args.input = None  # null out so _prepare_config doesn't use it

    config = _prepare_config(config_path, args)
    if args.force:
        config.analyze.skip_existing = False

    context_override = (getattr(args, "context", "") or "").strip() or None

    try:
        if args.command == "compress":
            run_compress_all(config, single_file=single_file)
        elif args.command == "analyze":
            run_analyze_all(config, single_file=single_file)
        elif args.command == "scripts":
            run_generate_scripts(config, single_file=single_file)
        elif args.command == "label":
            run_label_videos(config)
        elif args.command == "plan":
            run_plan_vlog(config, args.day)
        elif args.command == "run":
            run_full_pipeline(config, args.day)
        elif args.command == "refine":
            if not config.ai.context and not context_override:
                print(
                    "警告: config.yaml 里没有配置 ai.context 或 ai.context_file，"
                    "refine 效果有限（AI 不知道你的行程背景和规范）。",
                    file=sys.stderr,
                )
            fix = (getattr(args, "fix", "") or "").strip() or None
            target_path = getattr(args, "input", None)
            if fix and (target_path is None or target_path.is_dir()):
                print("错误: --fix 必须配合 -i 指定单个 .json 文件", file=sys.stderr)
                return 1
            try:
                if args.target in ("texts", "all"):
                    run_refine_texts(config, target_path, fix=fix, context_override=context_override)
                if args.target in ("scripts", "all"):
                    if args.target == "all" and target_path is not None:
                        scripts_path = None
                    else:
                        scripts_path = target_path
                    run_refine_scripts(config, scripts_path, fix=fix, context_override=context_override)
            except ValueError as e:
                print(f"错误: {e}", file=sys.stderr)
                return 1
        elif args.command == "cut":
            run_cut_all(
                config,
                day_label=args.day,
                output_dir=args.out_dir,
                reencode=args.reencode,
                source=args.source,
            )
        elif args.command == "serve":
            return run_ui(
                config,
                config_path=config_path,
                host=args.host,
                port=args.port,
                open_browser=not args.no_browser,
            )
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
```

Note: We mutate `args.input = None` here which is slightly dirty but safe since `_prepare_config` only reads `args.input` once. An alternative would be extracting input/output before `_prepare_config` and calling `apply_run_paths` manually, but that adds more code churn.

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `.venv/Scripts/python.exe -m pytest vlog_tool/tests/ -v`
Expected: 118 passed

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(cli): single-file detection + refine --context arg"
```

---

### Task 3: `pipeline.py` — `run_compress_all` single-file support

**Modify:** `vlog_tool/pipeline.py` — `run_compress_all` function (line 159)

- [ ] **Step 1: Add `single_file` param**

Change signature and add early-return:

```python
def run_compress_all(config: AppConfig, single_file: Path | None = None) -> list[ClipRecord]:
    if single_file:
        videos = [single_file]
    else:
        videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    
    # If single file, index starts after existing compressed files
    index_offset = 0
    if single_file:
        index_offset = _next_index(config.compressed_dir, config.naming.index_width) - 1
    
    config.compressed_dir.mkdir(parents=True, exist_ok=True)
    records: list[ClipRecord] = []

    with timed(f"run_compress_all（{len(videos)} 个）"):
        completed = 0
        elapsed_total = 0.0
        for i, video in enumerate(videos, start=1):
            idx = i + index_offset
            formatted_idx = format_index(idx, config.naming.index_width)
            out = config.compressed_dir / f"{formatted_idx}_{video.stem}.mp4"
            if config.analyze.skip_existing and out.exists():
                print(f"[跳过压缩] {video.name} (已存在: {out.name})")
            else:
                print(_eta_line("压缩", i, len(videos), video.name, completed, elapsed_total))
                t0 = time.monotonic()
                compress_video(video, out, config)
                elapsed_total += time.monotonic() - t0
                completed += 1
            records.append(ClipRecord(
                index=idx, stem=out.stem, source_path=video, compressed_path=out
            ))
    return records
```

- [ ] **Step 2: Run existing tests**

Run: `.venv/Scripts/python.exe -m pytest vlog_tool/tests/ -v`
Expected: 118 passed

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/pipeline.py
git commit -m "feat(pipeline): run_compress_all single-file support (-i single.mp4)"
```

---

### Task 4: `pipeline.py` — `run_analyze_all` single-file support

**Modify:** `vlog_tool/pipeline.py` — `run_analyze_all` function (line 182)

- [ ] **Step 1: Add `single_file` param**

```python
def run_analyze_all(config: AppConfig, tracker: ProgressTracker | None = None, single_file: Path | None = None) -> list[ClipRecord]:
    if single_file:
        videos = [single_file]
    else:
        videos = find_videos(config.paths.input_dir, recursive=config.paths.recursive)
    
    index_offset = 0
    if single_file:
        index_offset = _next_index(config.texts_dir, config.naming.index_width) - 1
    
    config.compressed_dir.mkdir(parents=True, exist_ok=True)
    config.texts_dir.mkdir(parents=True, exist_ok=True)

    print(f"素材目录: {config.paths.input_dir}（{'1 个视频' if single_file else f'{len(videos)} 个视频'}）")
    records: list[ClipRecord] = []
    ...
```

Then in the loop, change `idx = format_index(i, ...)` to `idx = format_index(i + index_offset, ...)`:

```python
            idx_val = i + index_offset
            idx = format_index(idx_val, config.naming.index_width)
```

And the `analysis["index"] = idx_val` (use int, not formatted string):

```python
            analysis["index"] = idx_val
            analysis["source_file"] = video.name

            stem = _build_stem(idx_val, analysis.get("title", video.stem), config)
```

Also the `records.append(ClipRecord(index=idx_val, ...))`:

```python
            records.append(ClipRecord(
                index=idx_val, stem=stem, source_path=video,
                compressed_path=compressed, text_path=final_text, analysis=analysis,
            ))
```

The full function changes require replacing:
- `for i, video in enumerate(videos, start=1):` body — change index from `i` to `i + index_offset`
- All `idx = format_index(i, ...)` calls → `idx_val = i + index_offset; idx = format_index(idx_val, ...)`
- `analysis["index"] = idx` → `analysis["index"] = idx_val`
- `_build_stem(i, ...)` → `_build_stem(idx_val, ...)`
- `ClipRecord(index=i, ...)` → `ClipRecord(index=idx_val, ...)`

- [ ] **Step 2: Run existing tests**

Run: `.venv/Scripts/python.exe -m pytest vlog_tool/tests/ -v`
Expected: 118 passed

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/pipeline.py
git commit -m "feat(pipeline): run_analyze_all single-file support (-i single.mp4)"
```

---

### Task 5: `pipeline.py` — `run_generate_scripts` single-file support

**Modify:** `vlog_tool/pipeline.py` — `run_generate_scripts` function (line 299)

- [ ] **Step 1: Add `single_file` param**

```python
def run_generate_scripts(config: AppConfig, tracker: ProgressTracker | None = None, single_file: Path | None = None) -> None:
    config.scripts_dir.mkdir(parents=True, exist_ok=True)
    template = config.script.template_file.read_text(encoding="utf-8") if config.script.template_file.exists() else ""

    if single_file:
        files = [single_file]
    else:
        files = sorted(config.texts_dir.glob("*.json"))
```

The `index_offset` logic isn't needed here because the index comes from the JSON content (`data.get("index", json_file.stem[:3])`), not from loop position.

- [ ] **Step 2: Run existing tests**

Run: `.venv/Scripts/python.exe -m pytest vlog_tool/tests/ -v`
Expected: 118 passed

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/pipeline.py
git commit -m "feat(pipeline): run_generate_scripts single-file support (-i single.json)"
```

---

### Task 6: `analyze.py` — Add `context_override` to `_wrap_with_context` and refine functions

**Modify:** `G:\Coding_Project\IdeaProjects\vlog-video-analysis\vlog_tool\analyze.py`

- [ ] **Step 1: Update `_wrap_with_context`**

```python
def _wrap_with_context(prompt: str, config: AppConfig, context_override: str | None = None) -> str:
    """如果有 trip 上下文/规范，附加在 prompt 前面。context_override 优先级高于 ai.context。"""
    parts = []
    if config.ai.context:
        parts.append(config.ai.context)
    if context_override:
        parts.append(context_override)
    if not parts:
        return prompt
    return (
        "## 背景与规范（请严格遵守）\n\n"
        f"{chr(10).join(parts)}\n\n"
        "---\n\n"
        f"{prompt}"
    )
```

- [ ] **Step 2: Update `refine_text` signature + pass `context_override`**

```python
def refine_text(analysis: dict, config: AppConfig, fix: str | None = None, context_override: str | None = None) -> dict:
    ...
    prompt = _wrap_with_context(base, config, context_override=context_override)
```

- [ ] **Step 3: Update `refine_script` signature + pass `context_override`**

```python
def refine_script(script: dict, analysis: dict | None, config: AppConfig, fix: str | None = None, context_override: str | None = None) -> dict:
    ...
    prompt = _wrap_with_context(base, config, context_override=context_override)
```

- [ ] **Step 4: Run existing tests**

Run: `.venv/Scripts/python.exe -m pytest vlog_tool/tests/ -v`
Expected: 118 passed

- [ ] **Step 5: Commit**

```bash
git add vlog_tool/analyze.py
git commit -m "feat(ai): add context_override param to _wrap_with_context and refine functions"
```

---

### Task 7: `pipeline.py` — Add `context_override` to refine pipeline functions

**Modify:** `vlog_tool/pipeline.py` — `run_refine_texts` (line 420) and `run_refine_scripts` (line 460)

- [ ] **Step 1: Update `run_refine_texts`**

```python
def run_refine_texts(config: AppConfig, path: Path | None = None, fix: str | None = None, context_override: str | None = None) -> int:
    ...
            try:
                refined = refine_text(analysis, config, fix=fix, context_override=context_override)
```

- [ ] **Step 2: Update `run_refine_scripts`**

```python
def run_refine_scripts(config: AppConfig, path: Path | None = None, fix: str | None = None, context_override: str | None = None) -> int:
    ...
            try:
                refined = refine_script(script, analysis, config, fix=fix, context_override=context_override)
```

- [ ] **Step 3: Run existing tests**

Run: `.venv/Scripts/python.exe -m pytest vlog_tool/tests/ -v`
Expected: 118 passed

- [ ] **Step 4: Commit**

```bash
git add vlog_tool/pipeline.py
git commit -m "feat(pipeline): add context_override to run_refine_texts/run_refine_scripts"
```

---

### Task 8: Final integration verification

- [ ] **Step 1: Run full test suite**

Run: `.venv/Scripts/python.exe -m pytest vlog_tool/tests/ -v`
Expected: 118 passed

- [ ] **Step 2: Verify `--help` output for new flags**

```bash
.venv/Scripts/python.exe main.py refine --help
```
Expected: `--context / -C` flag visible in help text.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(r003): CLI selective processing complete"
```
