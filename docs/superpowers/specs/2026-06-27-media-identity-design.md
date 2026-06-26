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

Introduce a `MediaIdentity` dataclass stored as `media_identity` in every generated
JSON artifact (analyze, transcript, plan). Consumers use `media_identity` fields
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
    segment_duration_sec: float | None  # None when parsed from filename (no .vmeta)
```

### JSON representation (written as `media_identity` in artifacts)

`_schema_version: 2` is the **top-level artifact version**. `media_identity` is a nested block.

```json
{
  "_schema_version": 2,
  "media_identity": {
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
    compressed_path: Path,
    input_dir: Path,
    index: str,
) -> MediaIdentity
```

Priority:
1. Read `.vmeta` sidecar (has `SplitInfo`, source_path, durations) — O(1), most accurate
2. Read `.vindex` for segment info if no `.vmeta` — O(1) per original stem
3. Fall back to filename parsing (current behavior) — works without sidecars

### `load_identity()`

```python
def load_identity(data: dict) -> MediaIdentity | None
```

Extracts `media_identity` from a JSON artifact dict.
Returns `None` for v1 (pre-identity) artifacts.

## Artifact Changes

### Analysis JSON (`texts/*.json`)

- On write in `_process_video_item()`: build `MediaIdentity` via `resolve_identity()`
- Add `media_identity` and `_schema_version: 2` to output dict
- (Existing fields unchanged: `index`, `source_file`, `title`, `summary`, etc.)

### Transcript JSON (`transcripts/*_transcript.json`)

- On write in `run_transcribe_all()`: build `MediaIdentity` via `resolve_identity()`
- On write in `run_transcribe_one()`: also build `MediaIdentity`
- Add `media_identity` and `_schema_version: 2` to output dict
- Keep `source_video` and `source_stem` for backward compat

### `ClipRecord` (`tasks/_helpers.py`)

- Add `identity: MediaIdentity | None = None` field
- Populated in `tasks/analyze.py` `_process_video_item()` after analysis completes

### Plan JSON (`plans/*_plan.json`)

- Each clip record in the plan output carries `media_identity` from the original analysis JSON
- Plan outputs get `_schema_version: 2` at top level
- Plan does not have a single `media_identity` (it aggregates multiple clips)

## Consumer Changes

### `tasks/plan.py` — Transcript injection fix

- Build `transcripts_map` keyed by `original_stem` instead of `source_stem` (compressed stem)
- For v2 transcripts: read `media_identity.original_stem` for map key
- For v1 transcripts: fall back to `source_stem` → `_extract_orig_stem()`
- Clip records in plan also carry analysis `media_identity` (propagated via `ClipRecord`)
- Clip `source_stem` in analysis JSON: for v2, use `media_identity.original_stem`; for v1, use existing fallback

### `export/jianying.py` — Source resolution

- For v2 artifacts: use `media_identity.original_stem` and `segment_offset_sec`
- Apply `segment_offset_sec` to source timerange when exporting split videos: `source_timerange.start += media_identity.segment_offset_sec`
- Fall back to `_resolve_video()` / `_resolve_video_by_prefix()` for v1 files

### `ui/routes/videos.py` — Sidecar matching

- For v2 text JSON: use `media_identity.original_stem` for transcript set lookup
- Use `media_identity.compressed_stem` for compressed→original matching
- Fall back to numeric prefix matching for v1 files

### `cut.py` — Offset support

- Add optional `offset_sec: float = 0.0` parameter
- When cutting from original for a split segment, add `offset_sec` to `-ss` argument
- Callers from JianYing export path provide `segment_offset_sec` from plan clip identity

## Backward Compatibility

- All v1 artifacts work unchanged (no `media_identity`, no `_schema_version`)
- `load_identity()` returns `None` for v1 → callers fall through to existing code paths
- Optional `migrate_v1_to_v2()` function can upgrade old artifacts in-place
- No migration is required — existing files continue to work via fallback paths

## Non-Goals

- Changing the on-disk file structure or naming convention (filenames stay the same)
- Rewriting cut/split/compress modules (identity is for consumer-side resolution)
- Adding UI for identity display (out of scope for Phase 2)
- Full schema migration CLI command (just the identity helpers for now)

## Test Guidance

### Unit tests for `vlog_tool/identity.py`

- `test_resolve_identity_with_vmeta`: mock `.vmeta` with `SplitInfo`, assert all fields populated
- `test_resolve_identity_with_vindex`: mock `.vindex` only, assert segment info populated
- `test_resolve_identity_fallback`: no sidecars, assert filename-parsed identity
- `test_load_identity_v2`: dict with `media_identity` block returns `MediaIdentity`
- `test_load_identity_v1`: dict without `media_identity` returns `None`
- `test_load_identity_corrupted`: dict with partial `media_identity` raises or returns `None`

### Integration tests

- `test_transcript_identity_written`: run transcribe on fixture, verify `media_identity` in output JSON
- `test_analysis_identity_written`: run analyze on fixture, verify `media_identity` in output JSON
- `test_plan_uses_original_stem_for_transcripts`: create v2 transcript and v2 analysis, assert transcript text appears in plan prompt
- `test_plan_v1_transcript_fallback`: create v1 transcript, assert fallback stem matching works
- `test_export_applies_segment_offset`: v2 plan with split identity, assert `source_timerange.start` includes `segment_offset_sec`
- `test_videos_route_v2_sidecar_matching`: seed v2 text JSON, assert videos route uses `media_identity` for transcript set

## Files to Create

- `vlog_tool/identity.py` — `MediaIdentity`, `resolve_identity()`, `load_identity()`

## Files to Modify

- `vlog_tool/tasks/_helpers.py` — add `identity` field to `ClipRecord`
- `vlog_tool/tasks/analyze.py` — add `media_identity` on write, populate `ClipRecord.identity`
- `vlog_tool/tasks/transcribe.py` — add `media_identity` on write in both `run_transcribe_all()` and `run_transcribe_one()`, fix transcript key
- `vlog_tool/tasks/plan.py` — key transcripts by `original_stem`, pass `media_identity` from clip records into plan output
- `vlog_tool/export/jianying.py` — use `media_identity`, apply `segment_offset_sec`
- `vlog_tool/ui/routes/videos.py` — use `media_identity` for sidecar matching and transcript set lookup
- `vlog_tool/cut.py` — add `offset_sec` parameter
