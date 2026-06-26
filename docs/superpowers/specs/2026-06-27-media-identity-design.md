# MediaIdentity — Canonical Media Identifier Design

Date: 2026-06-27  
Status: Draft  
Phase: 2 of project review remediation plan

## Problem

The project has no canonical media identity model. Four modules (`tasks/analyze.py`,
`tasks/transcribe.py`, `tasks/plan.py`, `export/jianying.py`) each implement their own
stem-parsing logic. This causes:

- Transcripts not injected into plan prompts (P1-002)
- Split-video offset not applied in export (P2-002)
- UI sidecar matching by fragile numeric prefix (P2-001)
- No shared `_schema_version` to distinguish file formats

## Solution

Introduce a `MediaIdentity` dataclass stored as `_media_identity` in every generated
JSON artifact (analyze, transcript, plan). Consumers use `_media_identity` fields
instead of guessing from filenames.

A `resolve_identity()` helper reads `.vmeta` sidecars first (most accurate), then
falls back to filename-prefix parsing for old files or files without sidecars.

## Data Model

### `MediaIdentity` dataclass (in `vlog_tool/identity.py`)

```python
@dataclass
class MediaIdentity:
    original_stem: str            # "GL010683"
    original_path: str            # full path to original video
    compressed_stem: str          # "001_GL010683" or "001_GL010683_seg01"
    compressed_path: str          # full path to compressed video
    index: str                    # "001"
    segment_index: int | None     # 1-based, None for non-split videos
    segment_offset_sec: float     # 0.0 for non-split videos
    segment_duration_sec: float | None
    _schema_version: int = 2      # artifact schema version
```

### JSON representation (written as `_media_identity` in artifacts)

```json
{
  "_schema_version": 2,
  "_media_identity": {
    "original_stem": "GL010683",
    "original_path": "G:/videos/GL010683.mp4",
    "compressed_stem": "001_GL010683_seg01",
    "compressed_path": "G:/output/compressed/001_GL010683_seg01.mp4",
    "index": "001",
    "segment_index": 1,
    "segment_offset_sec": 60.0,
    "segment_duration_sec": 60.0
  },
  "...existing fields...": "..."
}
```

## Key Functions

### `resolve_identity()`

```python
def resolve_identity(
    compressed_stem: str,
    compressed_dir: Path,
    input_dir: Path,
    index: str,
) -> MediaIdentity
```

Priority:
1. Read `.vmeta` sidecar (has `SplitInfo`, source_path, durations)
2. Read `.vindex` for segment info if no `.vmeta`
3. Fall back to filename parsing (current behavior)

### `load_identity()`

```python
def load_identity(data: dict) -> MediaIdentity | None
```

Extracts `_media_identity` from a JSON artifact dict.
Returns `None` for v1 (pre-identity) artifacts.

## Artifact Changes

### Analysis JSON (`texts/*.json`)

- On write in `_process_video_item()`: build `MediaIdentity` via `resolve_identity()`
- Add `_media_identity` and `_schema_version: 2` to output dict
- (Existing fields unchanged: `index`, `source_file`, `title`, `summary`, etc.)

### Transcript JSON (`transcripts/*_transcript.json`)

- On write in `run_transcribe_all()`: build `MediaIdentity` via `resolve_identity()`
- Add `_media_identity` and `_schema_version: 2` to output dict
- Keep `source_video` and `source_stem` for backward compat

### Plan JSON (`plans/*_plan.json`)

- On write in `run_plan_vlog()`: pass identity info through clip records
- Add `_schema_version: 2` to output (plan aggregates multiple clips, no single identity)

## Consumer Changes

### `tasks/plan.py` — Transcript injection fix

- Build `transcripts_map` keyed by `original_stem` instead of `source_stem` (compressed stem)
- For v2 transcripts: read `_media_identity.original_stem`
- For v1 transcripts: fall back to `source_stem` → `_extract_orig_stem()`
- Clip `source_stem` in analysis JSON also uses `original_stem`

### `export/jianying.py` — Source resolution

- For v2 artifacts: use `_media_identity.original_stem` and `segment_offset_sec`
- Apply `segment_offset_sec` to source timerange when exporting split videos
- Fall back to `_resolve_video()` / `_resolve_video_by_prefix()` for v1 files

### `ui/routes/videos.py` — Sidecar matching

- For v2 text JSON: use `_media_identity.original_stem` for transcript set lookup
- Use `_media_identity.compressed_stem` for compressed→original matching
- Fall back to numeric prefix matching for v1 files

### `cut.py` — Offset support

- Add optional `offset_sec: float = 0.0` parameter
- When cutting from original for a split segment, adjust `-ss` by `offset_sec`

## Backward Compatibility

- All v1 artifacts work unchanged (no `_media_identity`, no `_schema_version`)
- `load_identity()` returns `None` for v1 → callers fall through to existing code paths
- Optional `migrate_v1_to_v2()` function can upgrade old artifacts in-place

## Non-Goals

- Changing the on-disk file structure or naming convention
- Rewriting cut/split/compress modules (identity is for consumer-side resolution)
- Adding UI for identity display (out of scope for Phase 2)

## Files to Create

- `vlog_tool/identity.py` — `MediaIdentity`, `resolve_identity()`, `load_identity()`

## Files to Modify

- `vlog_tool/tasks/analyze.py` — add `_media_identity` on write
- `vlog_tool/tasks/transcribe.py` — add `_media_identity` on write, fix transcript key
- `vlog_tool/tasks/plan.py` — key transcripts by `original_stem`
- `vlog_tool/export/jianying.py` — use `_media_identity`, apply offset
- `vlog_tool/ui/routes/videos.py` — use `_media_identity` for matching
- `vlog_tool/cut.py` — add `offset_sec` parameter
