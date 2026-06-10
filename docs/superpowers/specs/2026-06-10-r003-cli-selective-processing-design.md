# R-003 CLI Selective Processing Design

## Overview

Allow CLI subcommands to operate on individual files (not just directories), and
add a `--context` flag to `refine` for temporary per-invocation context overrides.

## Changes

### 1. `-i` auto-detect: file vs directory

Three subcommands get single-file support — `compress`, `analyze`, `scripts`:

- `-i` pointing to a **video file** (`compress`/`analyze`) or **JSON file** (`scripts`) → process only that file
- `-i` pointing to a **directory** → keep existing behavior (process all files)
- index auto-assignment for single-file mode: scan existing output dir for max index + 1

**⚠️ Critical: `_prepare_config` interaction**

`apply_run_paths` sets `config.paths.input_dir = path.resolve()`. If `-i` points
to a file (not a directory), subsequent `find_videos(config.paths.input_dir)`
will fail because the path is a file, not a directory.

**Fix in `main.py`**: Before calling `_prepare_config`, detect if `args.input`
is a file. If so, save it as `single_file` and null out `args.input` so
`_prepare_config` doesn't set `input_dir` to a file path:

```python
single_file = None
input_val = getattr(args, "input", None)
if input_val and input_val.is_file():
    single_file = input_val
    input_val = None  # don't pass file to _prepare_config

config = _prepare_config(config_path, args_with_nulled_input)
```

Then pass `single_file` to the pipeline function.

**Index assignment for single-file:**

Add a `_next_index(scan_dir: Path, index_width: int = 3) -> int` helper that
scans `scan_dir` for `{index}_*` prefixed files and returns the next
available index (max existing + 1, defaulting to 1 if empty).

| Subcommand | Scan dir for `_next_index` |
|------------|---------------------------|
| `compress` | `config.compressed_dir` |
| `analyze`  | `config.texts_dir` (for JSON) |
| `scripts`  | `config.scripts_dir` (for `*_voiceover.json`) |

### 2. `scripts` gains `-i` single-JSON support

Currently `scripts` only accepts a directory. Add single `.json` file support:

```bash
python main.py scripts -i output/Franch/texts/001_xxx.json
```

→ Only generates voiceover for that one analysis JSON.

When `single_file` is provided to `run_generate_scripts`, skip
`config.texts_dir.glob("*.json")` and use `single_file` directly.

### 3. `refine --context / -C "临时说明"`

New CLI arg for `refine` subcommand:

```bash
python main.py refine --context "特别注意把戴高乐机场拼写改对"
```

- Passed as function parameter `context_override: str | None` through the
  full call chain: `main.py` → `run_refine_texts/run_refine_scripts` (pipeline)
  → `refine_text/refine_script` (analyze) → `_wrap_with_context`
- NOT stored in config dataclass (it's per-invocation state, not configuration)
- Prepended after `ai.context` in `_wrap_with_context()` with
  `\n---\n---\n` separator, higher priority than `ai.context`
- Only affects this single invocation, does not modify `config.yaml`

## Files to change

| File | Changes |
|------|---------|
| `main.py` | Add `--context` to refine parser; in dispatch, detect `-i` file before `_prepare_config`, save as `single_file`; pass `single_file` and `context_override` to pipeline functions |
| `pipeline.py` | `run_compress_all`/`run_analyze_all`/`run_generate_scripts` accept optional `single_file: Path`; add `_next_index()` helper; `run_refine_texts`/`run_refine_scripts` accept `context_override: str | None` |
| `analyze.py` | `refine_text`/`refine_script` accept `context_override`; `_wrap_with_context` accept `context_override` param |
| No changes to `config.py` | context_override is a function param, not a config field |

## No UI changes

This spec covers only CLI side of R-003 (sub-tasks a, b, c). UI sub-tasks (d, e, f, g) are deferred.
