# MediaIdentity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) for syntax tracking.

**Goal:** Define a canonical `MediaIdentity` dataclass and store it as `media_identity` in all generated JSON artifacts (analyze, transcript, plan), then fix consumers to use it instead of ad hoc filename parsing.

**Architecture:** Introduce `vlog_tool/identity.py` with `MediaIdentity` dataclass, `resolve_identity()` (reads .vmeta → .vindex → filename fallback), and `load_identity()` for v2 artifact deserialization. Each artifact writer adds `media_identity` on write. Each consumer reads `media_identity` first, falls back to existing logic for v1 files.

**Tech Stack:** Python 3.11+ dataclasses, Path, existing `VideoMeta`/`SplitInfo` in `vlog_tool/vmeta.py`, JSON filesystem artifacts.

---

### Task 1: identity.py + unit tests

**Files:**
- Create: `vlog_tool/identity.py`
- Create: `vlog_tool/tests/test_identity.py`

- [ ] **Step 1: Write `MediaIdentity` dataclass and `asdict()` helper**

`vlog_tool/identity.py`:
```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from vlog_tool.utils import find_videos
from vlog_tool.vmeta import VideoIndex, VideoMeta, SplitInfo


@dataclass
class MediaIdentity:
    original_stem: str
    original_path: str
    compressed_stem: str
    compressed_path: str
    index: str
    segment_index: int | None = None
    segment_offset_sec: float = 0.0
    segment_duration_sec: float | None = None


def _identity_to_dict(identity: MediaIdentity) -> dict:
    """Serialize MediaIdentity to a plain dict for JSON embedding."""
    d = asdict(identity)
    # Convert Path fields to strings (already str in this model)
    return d
```

- [ ] **Step 2: Write `resolve_identity()`**

```python
def _extract_original_stem(compressed_stem: str) -> str:
    """Extract original stem from a compressed file stem.

    Handles '001_GL010683' → 'GL010683', '001_GL010683_seg01' → 'GL010683',
    and 'GL010683' → 'GL010683'.
    """
    if "_" not in compressed_stem:
        return compressed_stem
    _, orig_stem = compressed_stem.split("_", 1)
    return re.sub(r"_seg\d+$", "", orig_stem)


def _find_original_by_stem(original_stem: str, input_dir: Path) -> Path | None:
    """Find an original video file by stem, searching input_dir recursively."""
    exts = (".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".m4v", ".webm", ".lrv")
    for ext in exts:
        candidate = input_dir / f"{original_stem}{ext}"
        if candidate.is_file():
            return candidate.resolve()
    for p in input_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts and p.stem.lower() == original_stem.lower():
            return p.resolve()
    return None


def resolve_identity(compressed_path: Path, input_dir: Path, index: str) -> MediaIdentity:
    """Build MediaIdentity from .vmeta sidecar first, fall back to filename parsing.

    Priority:
    1. .vmeta sidecar (most accurate, has SplitInfo with offset + duration)
    2. .vindex for segment info
    3. Filename parsing (works without sidecars)
    """
    compressed_stem = compressed_path.stem
    compressed_resolved = compressed_path.resolve()

    # Priority 1: Read .vmeta sidecar
    meta = VideoMeta.read(compressed_path)
    if meta is not None:
        si = meta.split_info
        return MediaIdentity(
            original_stem=si.original_stem if si else _extract_original_stem(compressed_stem),
            original_path=meta.source_path,
            compressed_stem=compressed_stem,
            compressed_path=str(compressed_resolved),
            index=index,
            segment_index=si.segment_index if si else None,
            segment_offset_sec=si.offset_sec if si else 0.0,
            segment_duration_sec=si.segment_duration_sec if si else None,
        )

    # Priority 2: Try .vindex for segment info
    original_stem = _extract_original_stem(compressed_stem)
    vindex = VideoIndex.read(original_stem, compressed_path.parent)
    if vindex is not None:
        seg_num = None
        offset_sec = 0.0
        seg_dur = None
        m = re.search(r"_seg(\d+)$", compressed_stem)
        if m:
            seg_num = int(m.group(1))
            for s in vindex.segments:
                if s.segment_number == seg_num:
                    offset_sec = s.offset_sec
                    seg_dur = s.duration_sec
                    break
        return MediaIdentity(
            original_stem=original_stem,
            original_path=vindex.source_path,
            compressed_stem=compressed_stem,
            compressed_path=str(compressed_resolved),
            index=index,
            segment_index=seg_num,
            segment_offset_sec=offset_sec,
            segment_duration_sec=seg_dur,
        )

    # Priority 3: Filename fallback
    orig_path = _find_original_by_stem(original_stem, input_dir)
    seg_num = None
    m = re.search(r"_seg(\d+)$", compressed_stem)
    if m:
        seg_num = int(m.group(1))
    return MediaIdentity(
        original_stem=original_stem,
        original_path=str(orig_path) if orig_path else "",
        compressed_stem=compressed_stem,
        compressed_path=str(compressed_resolved),
        index=index,
        segment_index=seg_num,
        segment_offset_sec=0.0,
        segment_duration_sec=None,
    )
```

- [ ] **Step 3: Write `load_identity()`**

```python
def load_identity(data: dict) -> MediaIdentity | None:
    """Extract MediaIdentity from a v2 JSON artifact.

    Returns None for v1 (pre-identity) artifacts.
    """
    raw = data.get("media_identity")
    if raw is None or not isinstance(raw, dict):
        return None
    try:
        return MediaIdentity(
            original_stem=str(raw["original_stem"]),
            original_path=str(raw.get("original_path", "")),
            compressed_stem=str(raw["compressed_stem"]),
            compressed_path=str(raw.get("compressed_path", "")),
            index=str(raw["index"]),
            segment_index=raw.get("segment_index"),
            segment_offset_sec=float(raw.get("segment_offset_sec", 0.0)),
            segment_duration_sec=raw.get("segment_duration_sec"),
        )
    except (KeyError, TypeError, ValueError):
        return None
```

- [ ] **Step 4: Write unit tests for identity.py**

`vlog_tool/tests/test_identity.py`:
```python
"""Tests for vlog_tool/identity.py — MediaIdentity, resolve_identity, load_identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vlog_tool.identity import MediaIdentity, _extract_original_stem, load_identity, resolve_identity
from vlog_tool.vmeta import SplitInfo, VideoMeta, VideoIndex, SegmentEntry


class TestExtractOriginalStem:
    def test_simple_compressed(self):
        assert _extract_original_stem("001_GL010683") == "GL010683"

    def test_with_seg_suffix(self):
        assert _extract_original_stem("001_GL010683_seg01") == "GL010683"

    def test_no_prefix(self):
        assert _extract_original_stem("GL010683") == "GL010683"

    def test_seg_no_prefix(self):
        assert _extract_original_stem("GL010683_seg01") == "GL010683"


class TestLoadIdentity:
    def test_v2_identity(self):
        data = {
            "_schema_version": 2,
            "media_identity": {
                "original_stem": "GL010683",
                "original_path": "/vids/GL010683.mp4",
                "compressed_stem": "001_GL010683",
                "compressed_path": "/out/comp/001_GL010683.mp4",
                "index": "001",
                "segment_index": None,
                "segment_offset_sec": 0.0,
                "segment_duration_sec": None,
            },
        }
        identity = load_identity(data)
        assert identity is not None
        assert identity.original_stem == "GL010683"
        assert identity.compressed_stem == "001_GL010683"
        assert identity.index == "001"
        assert identity.segment_index is None

    def test_v2_with_segment(self):
        data = {
            "media_identity": {
                "original_stem": "GL010683",
                "original_path": "/vids/GL010683.mp4",
                "compressed_stem": "001_GL010683_seg01",
                "compressed_path": "/out/comp/001_GL010683_seg01.mp4",
                "index": "001",
                "segment_index": 1,
                "segment_offset_sec": 60.0,
                "segment_duration_sec": 60.0,
            },
        }
        identity = load_identity(data)
        assert identity is not None
        assert identity.segment_index == 1
        assert identity.segment_offset_sec == 60.0

    def test_v1_no_identity(self):
        data = {"index": "001", "source_file": "GL010683.mp4"}
        assert load_identity(data) is None

    def test_empty_dict(self):
        assert load_identity({}) is None

    def test_corrupted_identity(self):
        data = {"media_identity": {"original_stem": "GL010683"}}  # missing required fields
        assert load_identity(data) is None


class TestResolveIdentityWithVmeta:
    def test_non_split_vmeta(self, tmp_path: Path):
        comp_dir = tmp_path / "compressed"
        comp_dir.mkdir()
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        # Create a dummy compressed file
        comp_path = comp_dir / "001_GL010683.mp4"
        comp_path.write_text("fake video")

        # Create dummy original file
        orig_path = input_dir / "GL010683.mp4"
        orig_path.write_text("fake original")

        # Create .vmeta sidecar
        meta = VideoMeta.build(
            source=orig_path,
            target=comp_path,
            source_duration=120.0,
            target_duration=60.0,
            is_original=False,
        )
        meta.write(comp_path)

        identity = resolve_identity(comp_path, input_dir, "001")
        assert identity.original_stem == "GL010683"
        assert identity.compressed_stem == "001_GL010683"
        assert identity.index == "001"
        assert identity.segment_index is None
        assert identity.segment_offset_sec == 0.0

    def test_split_vmeta(self, tmp_path: Path):
        comp_dir = tmp_path / "compressed"
        comp_dir.mkdir()
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        comp_path = comp_dir / "001_GL010683_seg01.mp4"
        comp_path.write_text("fake video")
        orig_path = input_dir / "GL010683.mp4"
        orig_path.write_text("fake original")

        # Create .vmeta with SplitInfo
        si = SplitInfo(
            original_stem="GL010683",
            segment_index=1,
            total_segments=2,
            offset_sec=60.0,
            segment_duration_sec=60.0,
        )
        meta = VideoMeta.build(
            source=orig_path,
            target=comp_path,
            source_duration=120.0,
            target_duration=60.0,
            split_info=si,
        )
        meta.write(comp_path)

        identity = resolve_identity(comp_path, input_dir, "001")
        assert identity.segment_index == 1
        assert identity.segment_offset_sec == 60.0
        assert identity.segment_duration_sec == 60.0
        assert identity.original_stem == "GL010683"


class TestResolveIdentityFallback:
    def test_filename_only(self, tmp_path: Path):
        comp_dir = tmp_path / "compressed"
        comp_dir.mkdir()
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        comp_path = comp_dir / "001_GL010683.mp4"
        comp_path.write_text("fake video")
        orig_path = input_dir / "GL010683.mp4"
        orig_path.write_text("fake original")

        identity = resolve_identity(comp_path, input_dir, "001")
        assert identity.original_stem == "GL010683"
        assert identity.segment_index is None
        assert identity.segment_offset_sec == 0.0

    def test_segmented_filename_no_vmeta(self, tmp_path: Path):
        comp_dir = tmp_path / "compressed"
        comp_dir.mkdir()
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        comp_path = comp_dir / "001_GL010683_seg02.mp4"
        comp_path.write_text("fake video")
        orig_path = input_dir / "GL010683.mp4"
        orig_path.write_text("fake original")

        identity = resolve_identity(comp_path, input_dir, "001")
        assert identity.original_stem == "GL010683"
        assert identity.segment_index == 2
        # No sidecar means offset/duration can't be determined
        assert identity.segment_offset_sec == 0.0
        assert identity.segment_duration_sec is None

    def test_original_not_found(self, tmp_path: Path):
        comp_dir = tmp_path / "compressed"
        comp_dir.mkdir()
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        comp_path = comp_dir / "001_GL010683.mp4"
        comp_path.write_text("fake video")
        # No original file exists

        identity = resolve_identity(comp_path, input_dir, "001")
        assert identity.original_stem == "GL010683"
        assert identity.original_path == ""  # not found


class TestResolveIdentityWithVindex:
    def test_vindex_provides_segment_info(self, tmp_path: Path):
        comp_dir = tmp_path / "compressed"
        comp_dir.mkdir()
        input_dir = tmp_path / "input"
        input_dir.mkdir()

        comp_path = comp_dir / "001_GL010683_seg01.mp4"
        comp_path.write_text("fake video")
        orig_path = input_dir / "GL010683.mp4"
        orig_path.write_text("fake original")

        # Create .vindex
        vindex = VideoIndex.build(
            source=orig_path,
            source_duration=120.0,
            segments=[
                SegmentEntry(
                    index="001",
                    filename="001_GL010683_seg01.mp4",
                    offset_sec=0.0,
                    duration_sec=60.0,
                    segment_number=1,
                    total_segments=2,
                ),
            ],
        )
        vindex.write(comp_dir)

        identity = resolve_identity(comp_path, input_dir, "001")
        assert identity.segment_index == 1
        # vindex provides offset and duration
        assert identity.segment_offset_sec == 0.0
        assert identity.segment_duration_sec == 60.0
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest vlog_tool/tests/test_identity.py -v
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add vlog_tool/identity.py vlog_tool/tests/test_identity.py
git commit -m "feat(identity): add MediaIdentity dataclass, resolve_identity, load_identity"
```

---

### Task 2: Add `media_identity` to analysis JSON

**Files:**
- Modify: `vlog_tool/tasks/analyze.py`
- Test: existing `test_analyze.py` or `test_analyze_funcs.py`

- [ ] **Step 1: Modify `_process_video_item` to write `media_identity`**

After `analysis["source_file"] = original.name`, add:
```python
from vlog_tool.identity import resolve_identity
# ...
identity = resolve_identity(compressed, config.paths.input_dir, idx_str)
analysis["_schema_version"] = 2
analysis["media_identity"] = _identity_to_dict(identity)
```

Need to import at the top:
```python
from vlog_tool.identity import MediaIdentity, resolve_identity, _identity_to_dict
```

- [ ] **Step 2: Run existing analysis tests to confirm no regression**

```bash
python -m pytest vlog_tool/tests/test_analyze.py vlog_tool/tests/test_analyze_funcs.py -v
```
Expected: All existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/tasks/analyze.py
git commit -m "feat(analyze): write media_identity into analysis JSON artifacts"
```

---

### Task 3: Add `media_identity` to transcript JSON + fix key

**Files:**
- Modify: `vlog_tool/tasks/transcribe.py`

- [ ] **Step 1: Add identity to `run_transcribe_all()`**

After resolving `original_video` and before building the transcript dict, add:
```python
identity = resolve_identity(compressed_video, config.paths.input_dir, compressed_stem.split("_", 1)[0] if "_" in compressed_stem else "")
transcript["_schema_version"] = 2
transcript["media_identity"] = _identity_to_dict(identity)
```

Import:
```python
from vlog_tool.identity import resolve_identity, _identity_to_dict
```

- [ ] **Step 2: Add identity to `run_transcribe_one()`**

After the segment dict is built:
```python
idx = video_path.stem.split("_", 1)[0] if "_" in video_path.stem else ""
identity = resolve_identity(video_path, config.paths.input_dir, idx)
transcript["_schema_version"] = 2
transcript["media_identity"] = _identity_to_dict(identity)
```

- [ ] **Step 3: Run existing transcribe tests**

```bash
python -m pytest vlog_tool/tests/test_transcribe.py -v
```
Expected: All existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add vlog_tool/tasks/transcribe.py
git commit -m "feat(transcribe): write media_identity into transcript JSON artifacts"
```

---

### Task 4: Add `identity` field to `ClipRecord`

**Files:**
- Modify: `vlog_tool/tasks/_helpers.py`
- Modify: `vlog_tool/tasks/analyze.py`

- [ ] **Step 1: Add `identity` field to ClipRecord**

In `vlog_tool/tasks/_helpers.py`:
```python
from vlog_tool.identity import MediaIdentity
# ...
@dataclass
class ClipRecord:
    index: int
    stem: str
    source_path: Path
    compressed_path: Path | None = None
    text_path: Path | None = None
    analysis: dict | None = None
    duration_sec: float = 0.0
    meta: VideoMeta | None = None
    identity: MediaIdentity | None = None   # <-- add this
```

- [ ] **Step 2: Populate identity in `_process_video_item()`**

After building the identity in Task 2, add:
```python
identity = resolve_identity(compressed, config.paths.input_dir, idx_str)
analysis["_schema_version"] = 2
analysis["media_identity"] = _identity_to_dict(identity)
```

And in the return statement:
```python
return ClipRecord(
    ...
    identity=identity,
)
```

Also in the skip-existing branch:
```python
# Build identity even for skipped files
identity = load_identity(existing_data) or resolve_identity(compressed, config.paths.input_dir, idx_str)
...
return ClipRecord(
    ...
    identity=identity,
)
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest vlog_tool/tests/test_analyze.py vlog_tool/tests/test_analyze_funcs.py -v
```
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add vlog_tool/tasks/_helpers.py vlog_tool/tasks/analyze.py
git commit -m "feat(helpers): add identity field to ClipRecord"
```

---

### Task 5: Fix plan transcript injection

**Files:**
- Modify: `vlog_tool/tasks/plan.py`

- [ ] **Step 1: Fix `transcripts_map` key to use `original_stem`**

In `run_plan_vlog()`, change the transcript loading section from:
```python
stem = data.get("source_stem", "")
if stem:
    transcripts_map[stem] = data
```
To:
```python
# Try v2 identity first, then fall back to v1 source_stem
identity = load_identity(data)
if identity is not None:
    stem = identity.original_stem
else:
    stem = _extract_orig_stem(data.get("source_stem", ""))
if stem:
    transcripts_map[stem] = data
```

Add import:
```python
from vlog_tool.identity import load_identity
```

- [ ] **Step 2: Fix clip `source_stem` to use `original_stem`**

In the clip-building section:
```python
source_stem = Path(data.get("source_file", "")).stem or json_file.stem
```
Change to:
```python
identity = load_identity(data)
if identity is not None:
    source_stem = identity.original_stem
else:
    source_stem = Path(data.get("source_file", "")).stem or json_file.stem
```

- [ ] **Step 3: Run plan tests**

```bash
python -m pytest vlog_tool/tests/test_plan.py -v
```
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add vlog_tool/tasks/plan.py
git commit -m "fix(plan): key transcripts by original_stem from media_identity"
```

---

### Task 6: Fix JianYing export to use `media_identity` + apply offset

**Files:**
- Modify: `vlog_tool/export/jianying.py`

- [ ] **Step 1: Update `_build_index_to_source()` to read `media_identity`**

Add a `load_identity` import and modify the function to prefer `media_identity.original_stem` over `source_file`:
```python
from vlog_tool.identity import load_identity

def _build_index_to_source(texts_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not texts_dir.is_dir():
        return mapping
    for p in sorted(texts_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        raw_idx = data.get("index")
        # Prefer media_identity for v2 artifacts
        identity = load_identity(data)
        if identity is not None:
            source = identity.original_stem
        else:
            source = data.get("source_file", "")
            if not source:
                continue
            source = Path(source).stem
        if raw_idx is None:
            continue
        idx_str = str(raw_idx)
        mapping[idx_str] = source
        mapping[idx_str.zfill(3)] = source
    return mapping
```

- [ ] **Step 2: Add `_build_index_to_offset()` helper and apply offset**

Add a function that reads `media_identity` from each analysis JSON to build index→offset mapping:
```python
from vlog_tool.identity import load_identity

def _build_index_to_offset(texts_dir: Path) -> dict[str, float]:
    """Read segment offsets from analysis JSON media_identity blocks.
    
    Returns {index_str: offset_sec} for split clips, empty dict for non-split.
    """
    offsets: dict[str, float] = {}
    if not texts_dir.is_dir():
        return offsets
    for p in sorted(texts_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        identity = load_identity(data)
        if identity is not None and identity.segment_offset_sec:
            offsets[identity.index] = identity.segment_offset_sec
    return offsets
```

Then modify `_build_tracks()` to accept and use offset mapping:
```python
def _build_tracks(
    plan_data: dict,
    index_to_material_id: dict[str, str],
    seq_text_ids: dict[int, str] | None = None,
    index_to_offset: dict[str, float] | None = None,
) -> list[dict]:
    ...
    offset = (index_to_offset or {}).get(idx, 0.0)
    source_start = _to_microseconds(start_sec + offset)
```

Update `export_plan_to_jianying()` to build and pass the offset mapping:
```python
index_to_offset = _build_index_to_offset(texts_dir) if texts_dir else {}
tracks = _build_tracks(plan_data, index_to_material_id, seq_text_ids, index_to_offset)
```

- [ ] **Step 3: Update export tests**

Check the existing `test_export.py` and update if needed:
```bash
python -m pytest vlog_tool/tests/test_export.py -v
```
Expected: Existing tests pass (v1 fallback path).

- [ ] **Step 4: Commit**

```bash
git add vlog_tool/export/jianying.py
git commit -m "fix(export): use media_identity for source resolution, apply segment offset"
```

---

### Task 7: Fix UI videos route to use `media_identity`

**Files:**
- Modify: `vlog_tool/ui/routes/videos.py`

- [ ] **Step 1: Use `media_identity` for transcript set lookup**

In `handle_get_videos()`, change the text sidecar reading to load `media_identity`:
```python
for td in _find_texts_dirs(proj_out):
    for f in sorted(td.iterdir()):
        if f.suffix != ".json" or "_" not in f.stem:
            continue
        idx = f.stem.split("_", 1)[0]
        text_sidecars.setdefault(idx, []).append(f.name)
        if idx not in text_titles:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                text_titles[idx] = data.get("title", "")
            except Exception:
                text_titles[idx] = ""
```

Change to also build `text_identities` mapping:
```python
text_identities: dict[str, MediaIdentity] = {}  # keyed by index
for td in _find_texts_dirs(proj_out):
    for f in sorted(td.iterdir()):
        if f.suffix != ".json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        idx = str(data.get("index", ""))
        if not idx:
            stem_parts = f.stem.split("_", 1)
            idx = stem_parts[0] if stem_parts[0].isdigit() else ""
        if not idx:
            continue
        text_sidecars.setdefault(idx, []).append(f.name)
        if idx not in text_titles:
            text_titles[idx] = data.get("title", "")
        if idx not in text_identities:
            identity = load_identity(data)
            if identity is not None:
                text_identities[idx] = identity
```

Then transcript matching changes from:
```python
"transcript_file": orig_stem if orig_stem and orig_stem in transcripts_set else None
```
To:
```python
"transcript_file": (identity.original_stem if (identity := text_identities.get(idx)) and identity.original_stem in transcripts_set else orig_stem if orig_stem and orig_stem in transcripts_set else None)
```
Or more readably:
```python
transcript_stem = None
if idx in text_identities and text_identities[idx].original_stem in transcripts_set:
    transcript_stem = text_identities[idx].original_stem
elif orig_stem and orig_stem in transcripts_set:
    transcript_stem = orig_stem
```

- [ ] **Step 2: Run video route tests**

```bash
python -m pytest vlog_tool/tests/test_server.py -v -k "video"
```
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/ui/routes/videos.py
git commit -m "fix(ui): use media_identity for transcript matching in videos route"
```

---

### Task 8: Add `offset_sec` to `cut.py`

**Files:**
- Modify: `vlog_tool/cut.py`

- [ ] **Step 1: Add `offset_sec` parameter**

```python
def cut_one(
    video_path: Path,
    output_path: Path,
    start_sec: float,
    end_sec: float,
    ffmpeg: str,
    reencode: bool = False,
    cancel_event: threading.Event | None = None,
    offset_sec: float = 0.0,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    adjusted_start = start_sec + offset_sec
    duration_sec = end_sec - start_sec  # duration stays the same
    label = f"裁剪 {video_path.name} ({format_duration(adjusted_start)}-{format_duration(end_sec + offset_sec)})"
    args = [
        "-ss",
        str(adjusted_start),
        "-i",
        str(video_path),
        "-t",
        str(duration_sec),
    ]
    ...
```

- [ ] **Step 2: Run cut tests**

```bash
python -m pytest vlog_tool/tests/ -v -k "cut"
```

- [ ] **Step 3: Commit**

```bash
git add vlog_tool/cut.py
git commit -m "feat(cut): add offset_sec parameter for split segment cutting"
```

---

### Task 9: Full regression test

- [ ] **Step 1: Run all tests**

```bash
python -m pytest vlog_tool/tests/ -v
```
Expected: All existing tests pass, no regressions.

- [ ] **Step 2: Run lint check**

```bash
ruff check vlog_tool/identity.py vlog_tool/tasks/ vlog_tool/export/ vlog_tool/ui/routes/videos.py vlog_tool/cut.py
```

- [ ] **Step 3: Format check**

```bash
ruff format --check vlog_tool/identity.py vlog_tool/tasks/ vlog_tool/export/ vlog_tool/ui/routes/videos.py vlog_tool/cut.py
```

- [ ] **Step 4: (If all pass) Final commit for any remaining changes**

```bash
git add -A
git commit -m "chore: finalize Phase 2 — media identity integration"
```
