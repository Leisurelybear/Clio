# Design: Remove physical video split (logical analyze windows)

**Date**: 2026-07-18  
**Status**: Draft — approved in design dialogue; not implemented  
**Scope**: Stop treating ffmpeg physical segments (`_segNN`) as first-class media identity. Keep long-video AI analysis via **in-analyze logical windows** (temp ffmpeg slices → multi Gemini call → one absolute-timeline artifact). Legacy split projects remain **read-only compatible**.  
**Approach**: Phased P0 → P1 → P2 → P3 (P4 optional cleanup). Single `is_legacy_split_*` gate; new pipeline never writes split identity.

## 1. Goals and non-goals

### Goals

1. **Kill segment-as-identity**: New pipeline: 1 original → 1 compressed → 1 analysis / script (and prefer 1 transcript) → plan usually references 1 clip index per original.
2. **Keep long-video analyzable**: Clips longer than a window still get full coverage via sliding windows inside `analyze` only.
3. **One timebase**: Artifact timelines are **absolute on the original** (0 = original start). Downstream cut / export / UI / transcript do not add `segment_offset` on new data.
4. **Legacy read-only**: Existing `_seg*` corpora, plans, and exports keep working through a single legacy path. No forced migrate.
5. **Concentrate complexity**: Multi-part logic is allowed only inside analyze (and the legacy gate). New code must not reintroduce `_seg` regexes elsewhere.

### Non-goals

- Scene-detect / smart shot boundaries for windows.
- Preferring Gemini native `start_offset` / `end_offset` (may be revisited later; **not** this design).
- One-shot auto-migrate of multi-seg artifacts into a single identity (optional follow-up).
- Changing compress quality policy (fps / max_width / remove_audio / target size defaults stay).
- Reworking plan UI, JianYing draft schema, or waveform product design beyond dropping segment-only branches for new data.
- Writing partial texts when some windows fail (explicitly rejected — whole clip fails).

### Success criteria

- New projects: no `output/splits/` staging, no `*_split_manifest.json`, no `_segNN` compressed names, no multi-row original expansion for new compress output.
- Long clip (e.g. 40 min) produces **one** texts JSON whose event times are absolute; all windows must succeed or nothing is written.
- Legacy projects: list / play / texts / cut / export behavior matches today via `is_legacy_split_*`.
- New-path cut / export / viewer: `offset` formula uses `segment_offset_sec` only when legacy; new identities always 0.
- Config: `window_max_min` / `window_overlap_sec` drive analyze; `compress.split_*` deprecated no-ops for new runs.

## 2. Problem statement (why split is a liability)

Physical split was introduced so long vlogs could be uploaded to Gemini under duration / size pressure (`split_max_min` default 15, plus `max_analyze_duration_min` skip gate). Compression already shrinks media (e.g. 640p, low fps, strip audio).

The mistake was **promoting an analyze constraint into global media identity**:

| Layer | Cost today |
| --- | --- |
| Identity | `SplitInfo`, `.vindex` multi-seg, `MediaIdentity.segment_*`, filename `_segNN` |
| Pipeline | compress staging, dual skip paths, per-seg analyze/transcribe/script |
| Time | Segment-local vs original-absolute dual timebase |
| UI | Group rows, boundary auto-switch, segment-specific sidecar match, waveform `is_segment` |
| Export / cut | `index_to_offset`, cut `+ offset` |
| History | B-060 / B-068 / B-073 / B-097 and related identity bugs |

Rough surface: tens of production modules and heavy test density around split. New features repeatedly re-ask “whole clip or segment?”

**Correct boundary**: long-video handling stays inside analyze. Downstream only sees whole originals / single compressed files.

## 3. Decisions (locked)

| Topic | Decision |
| --- | --- |
| Architecture | **Logical analyze windows**; no new physical segment identity |
| Window media | **Temp ffmpeg slice** of the **already-compressed** file per window |
| Legacy | **Read-only compatible** (no forced migrate) |
| Partial window failure | **Whole analyze fails**; do not write texts |
| Config | New `analyze.window_max_min` + `window_overlap_sec`; deprecate compress split knobs |
| Rollout | P0 gate → P1 compress → P2 analyze windows → P3 downstream/UI → P4 optional delete legacy code |

## 4. Target identity and storage

### 4.1 Canonical (new)

```
Original video
  └── compressed:  {index}_{original_stem}.mp4     # never _segNN
        ├── .vmeta                                 # split_info = null
        ├── .vindex (optional single entry)        # is_split = false
        ├── texts:   one JSON, absolute times
        ├── scripts: one JSON
        └── transcripts: prefer one original-absolute file
```

`MediaIdentity` on new writes:

- `original_*`, `compressed_*`, `index` as today
- `segment_index` / `segment_offset_sec` / `segment_duration_sec` → **null / 0 / null** (fields may remain for JSON compatibility; must not carry real segment semantics)

Optional debug block on analysis JSON (not a list-row identity):

```json
"analyze_windows": [
  {"i": 0, "start_sec": 0, "end_sec": 900, "overlap_sec": 20, "status": "ok"},
  {"i": 1, "start_sec": 880, "end_sec": 1800, "overlap_sec": 20, "status": "ok"}
]
```

### 4.2 Legacy (read-only)

Existing layout unchanged:

```
output/splits/…_segNN.mp4
compressed/{idx}_{stem}_segNN.mp4 + .vmeta.split_info
{stem}.vindex (multi), {stem}_split_manifest.json
N texts / scripts / transcripts / plan indices
```

### 4.3 Legacy detection (single gate)

Centralize in `clio/identity.py` (or a tiny dedicated module imported by identity):

```text
is_legacy_split(...) is true if any of:
  1. vmeta.split_info is not None
  2. compressed stem matches segment suffix (_segNN; include _part/_pt/_chunk if already supported in videos API)
  3. related .vindex has is_split and len(segments) > 1 and this file is one of those segments
```

All new branches: `if is_legacy_split(...): legacy_path else: unified_path`.  
**Forbidden**: third ad-hoc `_seg` parsers in UI/tasks.

### 4.4 What new path must not write

- `output/<splits_subdir>/` staging segments
- `*_split_manifest.json`
- `_segNN` (or aliases) in compressed basenames
- non-null `split_info` on new `.vmeta`

## 5. Analyze windows (core)

### 5.1 When to window

```text
duration = ffprobe(compressed)
window_max = window_max_min * 60
overlap    = window_overlap_sec

if duration <= window_max:
    windows = [(0, duration)]   # single window; skip merge complexity
else:
    slide with step (window_max - overlap); last window ends at duration
```

Defaults (project analyze section):

| Key | Default | Role |
| --- | --- | --- |
| `analyze.window_max_min` | `15` | Target max seconds per Gemini upload slice |
| `analyze.window_overlap_sec` | `20` | Overlap for boundary dedupe |
| `analyze.max_analyze_duration_min` | `0` (new default / examples) | **Whole-clip hard cap**; `0` = unlimited. Skip entire clip if over (quota safety). Windowing is the normal length control |

**Config migration note:** Existing project YAML values are left as-is on load. Only dataclass / `project.example.yaml` defaults change. A project that still has `max_analyze_duration_min: 30` will skip a 40‑minute *whole* compressed file until windows (P2) exist **or** the user raises/zeros the cap. After P2, windows are the primary length control; a high or zero hard cap is recommended.

Deprecated (still readable so old YAML does not break; **ignored on new compress**):

- `compress.split_max_min`
- `compress.splits_subdir`
- `compress.reencode_split`

### 5.2 Temp slice upload

For each window `[start, end)`:

1. Write under `output/.analyze_windows/` (project-local, gitignored if needed):  
   `{compressed_stem}_w{i:02d}_{start}-{end}.mp4`
2. ffmpeg from **compressed** parent: prefer `-ss` before `-i`, `-t`, `-c copy`; on failure or bad duration, light re-encode fallback.
3. Upload temp file to Gemini (existing 200MB guard applies).
4. On window success, delete temp file; on full job end, sweep directory for orphans.
5. Honor `cancel_event`: stop scheduling further windows; if not all windows ok, **do not** write final texts.

Slices must **not** land in `compressed/`, must not get pipeline indices, must not appear in `/api/videos`.

If a single window file still exceeds upload limit: one level of bisection (or fail that window → whole clip fails). Do not invent a second identity system.

### 5.3 Prompt and time normalization

- Reuse existing video-analyze prompt structure for regression safety.
- Model sees slice-local time starting at 0.
- After JSON parse, add `window.start_sec` to every temporal field (timeline / events / mm:ss helpers already in codebase).
- Optional one-line context in prompt: this slice is original `[start, end)` seconds; times are slice-local.

### 5.4 Merge rules

Inputs: window results already converted to **absolute** time.  
Output: one analysis dict + `analyze_windows` metadata.

| Field class | Rule |
| --- | --- |
| Timeline / event lists | Concatenate, sort by start; dedupe inside overlap |
| Overlap dedupe | Same overlap region, start within ~5s, high title/desc similarity → keep richer row |
| Title | Prefer window 0 |
| Summary / description | Concatenate in time order (no mandatory second LLM; optional later refine) |
| Tags / places / people | Set-union |
| Scores | Average or max per existing field semantics; drop if unclear |
| Single window | No merge pipeline; write through as today |

### 5.5 Failure policy (locked)

- Per-window: provider retries as today; still failing → window failed.
- **Any** window failed after retries → **entire clip analyze fails**; no texts file.
- All windows fail → same.
- Cancel mid-run → no final texts.
- `skip_existing`: existing complete texts → skip; missing or failed prior run → run. No “partial success” artifact.

### 5.6 Pipeline item enumeration

```text
if is_legacy_split(compressed):
    analyze as today (one call per segment file; segment-local + identity offset)
else:
    analyze_with_windows(compressed) → one JSON absolute
```

New `run_analyze` must **not** expand a single original into N items via multi-seg `.vindex` for non-legacy files.

## 6. Downstream behavior

### 6.1 Compress (P1)

- Always 1 original → 1 compressed; ignore `split_max_min` even if > 0.
- Write single-entry `.vindex` (`is_split=false`) so lookup helpers keep working.
- Do not delete existing `_seg*` files automatically (avoid data loss).
- Log when legacy segments exist beside a new whole-file compress; user may re-analyze / re-plan.

### 6.2 Transcribe / align

| | New | Legacy |
| --- | --- | --- |
| Transcript | Prefer one original-absolute transcript | Per-seg + offset align as today |
| Align | No segment_offset injection | Keep `segment_offset_sec` when remove_audio |

### 6.3 Script / plan

| | New | Legacy |
| --- | --- | --- |
| Scripts | One per index / original | Per segment index |
| Plan clips | Absolute `use_timeline`; identity offset 0 | Existing offset fields |
| Plan prompt input | One merged analysis blob per clip | Multi-seg summaries |

**Mixed re-run warning**: if user re-compresses a legacy project into whole-file identity, old plan indices may not map — require re-analyze + re-plan. No silent remapping.

### 6.4 Cut / JianYing

Shared formula:

```text
offset = identity.segment_offset_sec if is_legacy_split_identity(identity) else 0.0
apply start/end with + offset on original material
```

New writes always yield offset 0, so one code path remains correct for both.

### 6.5 UI / API

| Surface | New | Legacy |
| --- | --- | --- |
| Video list | One row per original / compressed pair | Keep group_key, segment_label, multi-row, segment_matches |
| Play original | Full file, no boundary auto-jump | Keep auto-switch across segments |
| Texts / voiceover | One sidecar set | Segment-specific match (B-097 behavior) |
| Waveform | Normal path (no is_segment special case required) | Keep is_segment duration match |
| Config UI | Expose window_* ; deprecate split_* (still loadable) | — |

**Coexistence**: if both `_seg*` rows and a new whole compressed file exist, **show both**; match sidecars by exact compressed stem first so new files do not steal seg sidecars.

## 7. Phasing

| Phase | Name | Deliverable | Behavior change |
| --- | --- | --- | --- |
| **P0** | Legacy gate | `is_legacy_split_*` + tests; call sites start using it where cheap | No user-visible change |
| **P1** | Compress unsplit | Stop calling `split_video` on new runs; single vmeta/vindex | New compress = 1 file; long clips not yet multi-window analyzed |
| **P2** | Analyze windows | Temp slices, multi-call, merge, fail-closed | Long clips analyzable as one artifact |
| **P3** | Downstream / UI | Transcribe preference, list/play simplified for new data, config labels, docs/README | End-to-end “no seg” UX for new projects |
| **P4** | Cleanup (optional) | Remove dead split write path, shrink tests, hide deprecated knobs | After active legacy projects are rare |

**Order is fixed: P0 → P1 → P2 → P3.**  
Note: after P1 and before P2, very long single compressed files may hit `max_analyze_duration_min` or quality/size limits — ship P2 soon after P1, or temporarily keep a high whole-clip cap only with windows enabled.

Each phase is separately mergeable and revertable.

## 8. Testing strategy

| Area | Focus |
| --- | --- |
| P0 | Gate true/false matrix: plain file, `_seg`, vmeta.split_info, vindex multi |
| P1 | compress never creates `_seg` / splits dir / manifest; skip_existing by whole stem |
| P2 | window geometry; single-window passthrough; multi-window merge + overlap dedupe; any window fail → no texts; cancel → no texts; temp cleanup |
| P3 | cut/export offset 0 on new identity; legacy fixtures still offset; UI list single row for new fixtures |
| Legacy regression | Minimal fixtures only — do not grow new split cases |

Prefer mock ffmpeg / mock Gemini (project test style).

## 9. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Dual-path mess during transition | One gate function; ban new `_seg` parsers |
| P1 without P2 leaves long clips stuck | Sequence P2 immediately; document interim |
| Window boundary misses / dupes | 20s overlap + dedupe; tune later |
| Disk fill from temp slices | Per-window delete + end sweep under `.analyze_windows/` |
| Old plan + new compress index mismatch | Explicit user message; no silent map |
| Single compressed file huge | Windows upload slices, not whole file; 200MB guard + optional bisect |
| Reindex / helpers still assume multi-seg | P3 audit of `reindex`, `file_service`, `index.lookup` |

## 10. Docs / product copy impact

- README “自动分段（15min）” → long-video **analyze windows** (not physical split).
- `docs/project.example.yaml` / descriptions: window keys; split keys marked deprecated.
- ROADMAP: track as R-xxx (assign when implementing); link this spec.
- Related historical specs remain valid as **legacy** description: UI segment grouping, media identity segment fields, vmeta multi-seg — not deleted, but superseded for new writes by this document.

## 11. Open follow-ups (out of scope)

- Optional migrate command: merge legacy multi-seg artifacts → single identity.
- Optional Gemini API native offsets to avoid temp files.
- Optional second-pass text refine to stitch multi-window summaries.
- Optional allow_partial_windows (rejected for v1).

## 12. Summary diagram

```text
BEFORE
  Original ──split──► N staging ──compress──► N indexed files
       ──analyze N──► N texts (local time) ──► plan N indices
       ──cut/export──► + segment_offset everywhere

AFTER (new)
  Original ──compress──► 1 file
       ──analyze──► [temp slice w0..wK → Gemini] ──merge──► 1 texts (absolute)
       ──plan/cut/export/UI──► no segment identity

AFTER (legacy read)
  Existing _seg* tree ── is_legacy_split ──► today’s offset paths
```
