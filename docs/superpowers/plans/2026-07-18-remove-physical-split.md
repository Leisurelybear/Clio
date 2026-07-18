# Remove Physical Split (Logical Analyze Windows) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop writing physical `_segNN` media identity; analyze long clips via temp ffmpeg windows merged into one absolute-timeline texts JSON; keep legacy split projects read-only compatible.

**Architecture:** Single `is_legacy_split_*` gate. New compress always 1:1. New analyze builds time windows, slices the compressed file under `output/.analyze_windows/`, multi-calls Gemini, merges with absolute times, fail-closed (any window fail → no texts). Downstream uses `segment_offset_sec` only when legacy.

**Tech Stack:** Python 3.11+, pytest + unittest.mock, existing `clio.split`/`ffmpeg` helpers, `clio.identity`, `clio.tasks.analyze`, vanilla JS config UI.

**Spec:** `docs/superpowers/specs/2026-07-18-remove-physical-split-design.md`

## Global Constraints

- Work on `main`; one logical commit per task; **ask before push**.
- Chinese user-facing copy; English commits (`type(scope): subject`).
- Tests default: mock-style (monkeypatch / unittest.mock), no real ffmpeg/Gemini in unit tests.
- New code must not invent a third `_seg` parser — only `is_legacy_split_*` (+ existing legacy readers).
- Window failure policy: **whole clip fails, do not write texts**.
- Do not auto-delete existing `_seg*` files on disk.
- After P1 and before P2, long whole-file clips may hit `max_analyze_duration_min`; ship P2 immediately after P1 (or in the same session).
- Do not change compress quality defaults (fps/width/remove_audio) except deprecating split knobs’ **effect**.

## File map

| Path | Role |
| --- | --- |
| `clio/identity.py` | `SEGMENT_SUFFIX_RE`, `is_legacy_split_path`, `is_legacy_split_identity`, `legacy_segment_offset_sec` |
| `clio/tests/test_identity.py` | Gate matrix tests |
| `clio/tasks/compress.py` | Stop calling `split_video`; always compress original |
| `clio/tests/test_tasks_compress.py` | Assert no split even when `split_max_min>0` |
| `clio/config/models.py` | `window_max_min`, `window_overlap_sec`; default `max_analyze_duration_min=0` |
| `clio/config/loader.py` | Load new keys |
| `clio/config/validators.py` | Validate new keys |
| `clio/config/descriptions.py` | Chinese descriptions; deprecate split copy |
| `docs/project.example.yaml` / `config.example.yaml` | Examples |
| `clio/analyze_windows.py` (**new**) | Pure window geometry + merge + temp slice helpers |
| `clio/tests/test_analyze_windows.py` (**new**) | Unit tests for windows/merge/slice |
| `clio/tasks/analyze.py` | Branch legacy vs `analyze_with_windows` |
| `clio/tests/test_tasks_analyze.py` | Window path + fail-closed |
| `clio/tasks/cut.py` | Offset via `legacy_segment_offset_sec` |
| `clio/export/jianying.py` | Same |
| `clio/ui/static/src/editor-config.js` | Labels for window_* ; soft-deprecate split |
| `clio/ui/routes/config_routes.py` | If field allowlists exist, add keys |
| `README.md` / `README.en.md` / `ROADMAP.md` | Product copy + R-xxx entry |
| `.gitignore` | Optional `**/.analyze_windows/` |

---

### Task 1: Legacy split gate (P0)

**Files:**
- Modify: `clio/identity.py`
- Modify: `clio/tests/test_identity.py`

**Interfaces:**
- Produces:
  - `SEGMENT_SUFFIX_RE: re.Pattern` — matches `_seg|_part|_pt|_chunk` + digits at end of stem (case-insensitive), same idea as `videos.py` `_SEG_RE` but applied to full compressed stem or rest-after-index.
  - `is_legacy_split_stem(stem: str) -> bool`
  - `is_legacy_split_path(compressed_path: Path) -> bool` — true if vmeta.split_info, or stem suffix, or multi-seg vindex membership
  - `is_legacy_split_identity(identity: MediaIdentity | None) -> bool` — true if `segment_index is not None` or `segment_offset_sec != 0` or stem looks segmented
  - `legacy_segment_offset_sec(identity: MediaIdentity | None) -> float` — returns `identity.segment_offset_sec` if legacy else `0.0`

- [ ] **Step 1: Write the failing tests**

Append to `clio/tests/test_identity.py`:

```python
from clio.identity import (
    is_legacy_split_identity,
    is_legacy_split_path,
    is_legacy_split_stem,
    legacy_segment_offset_sec,
)


class TestIsLegacySplit:
    def test_stem_plain(self):
        assert is_legacy_split_stem("001_GL010683") is False

    def test_stem_seg(self):
        assert is_legacy_split_stem("001_GL010683_seg01") is True

    def test_stem_part_alias(self):
        assert is_legacy_split_stem("001_GL010683_part02") is True

    def test_path_vmeta_split_info(self, tmp_path: Path):
        src = tmp_path / "GL.mp4"
        src.write_bytes(b"\x00" * 100)
        compressed = tmp_path / "001_GL.mp4"
        compressed.write_bytes(b"\x00" * 50)
        meta = VideoMeta.build(
            source=src,
            target=compressed,
            source_duration=100.0,
            target_duration=50.0,
            split_info=SplitInfo(
                original_stem="GL",
                segment_index=1,
                total_segments=2,
                offset_sec=0.0,
                segment_duration_sec=50.0,
            ),
        )
        meta.write(compressed)
        assert is_legacy_split_path(compressed) is True

    def test_path_plain_vmeta(self, tmp_path: Path):
        src = tmp_path / "GL.mp4"
        src.write_bytes(b"\x00" * 100)
        compressed = tmp_path / "001_GL.mp4"
        compressed.write_bytes(b"\x00" * 50)
        VideoMeta.build(
            source=src,
            target=compressed,
            source_duration=100.0,
            target_duration=100.0,
        ).write(compressed)
        assert is_legacy_split_path(compressed) is False

    def test_identity_helpers(self):
        plain = MediaIdentity(
            original_stem="GL",
            original_path="/GL.mp4",
            compressed_stem="001_GL",
            compressed_path="/c/001_GL.mp4",
            index="001",
        )
        split = MediaIdentity(
            original_stem="GL",
            original_path="/GL.mp4",
            compressed_stem="001_GL_seg02",
            compressed_path="/c/001_GL_seg02.mp4",
            index="001",
            segment_index=2,
            segment_offset_sec=900.0,
            segment_duration_sec=900.0,
        )
        assert is_legacy_split_identity(plain) is False
        assert is_legacy_split_identity(split) is True
        assert legacy_segment_offset_sec(plain) == 0.0
        assert legacy_segment_offset_sec(split) == 900.0
        assert legacy_segment_offset_sec(None) == 0.0
```

- [ ] **Step 2: Run tests — expect FAIL (import/name missing)**

```bash
pytest clio/tests/test_identity.py::TestIsLegacySplit -v
```

Expected: `ImportError` or `AttributeError` for missing symbols.

- [ ] **Step 3: Implement gate in `clio/identity.py`**

Add near top (after imports):

```python
# Align with clio/ui/routes/videos.py segment aliases
SEGMENT_SUFFIX_RE = re.compile(r"(?i)_(?:seg|part|pt|chunk)(\d+)$")


def is_legacy_split_stem(stem: str) -> bool:
    return SEGMENT_SUFFIX_RE.search(stem) is not None


def is_legacy_split_path(compressed_path: Path) -> bool:
    meta = VideoMeta.read(compressed_path)
    if meta is not None and meta.split_info is not None:
        return True
    if is_legacy_split_stem(compressed_path.stem):
        return True
    original_stem = _extract_original_stem(compressed_path.stem)
    vindex = VideoIndex.read(original_stem, compressed_path.parent)
    if vindex is not None and vindex.is_split and len(vindex.segments) > 1:
        name = compressed_path.name
        if any(s.filename == name for s in vindex.segments):
            return True
    return False


def is_legacy_split_identity(identity: MediaIdentity | None) -> bool:
    if identity is None:
        return False
    if identity.segment_index is not None:
        return True
    if abs(float(identity.segment_offset_sec or 0.0)) > 1e-6:
        return True
    return is_legacy_split_stem(identity.compressed_stem)


def legacy_segment_offset_sec(identity: MediaIdentity | None) -> float:
    if not is_legacy_split_identity(identity):
        return 0.0
    assert identity is not None
    return float(identity.segment_offset_sec or 0.0)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest clio/tests/test_identity.py::TestIsLegacySplit -v
```

- [ ] **Step 5: Commit**

```bash
git add clio/identity.py clio/tests/test_identity.py
git commit -m "feat(identity): add is_legacy_split gate for unified media path"
```

---

### Task 2: Compress never physical-splits (P1)

**Files:**
- Modify: `clio/tasks/compress.py` (`run_compress_all` Phase 1 loop ~125–144)
- Modify: `clio/tests/test_tasks_compress.py`

**Interfaces:**
- Consumes: existing `compress_video`, `VideoMeta.build` without split_info
- Produces: always `items = [(video, video), ...]` for new runs (ignore `split_max_min`)

- [ ] **Step 1: Write the failing test**

```python
# in TestRunCompressAll
def test_ignores_split_max_min(self, monkeypatch, tmp_path: Path):
    cfg = _cfg(tmp_path)
    cfg.compress.split_max_min = 15  # would have split historically
    _add_video(cfg, "long_clip.mp4")

    split_calls = []

    def _spy_split(*a, **kw):
        split_calls.append((a, kw))
        return [a[0]]

    monkeypatch.setattr("clio.tasks.compress.resolve_binary", lambda *a: "ffmpeg")
    monkeypatch.setattr("clio.tasks.compress.split_video", _spy_split)
    monkeypatch.setattr(
        "clio.tasks.compress.compress_video",
        lambda inp, outp, c, **kw: outp.write_bytes(b"\x00" * 300) or outp,
    )
    monkeypatch.setattr("clio.tasks.compress.get_duration_sec", lambda *a, **k: 3600.0)
    monkeypatch.setattr("clio.tasks.compress._safe_duration", lambda *a, **k: 3600.0)

    records = run_compress_all(cfg)
    assert split_calls == []
    assert len(records) == 1
    assert records[0].compressed_path is not None
    assert "_seg" not in records[0].compressed_path.name
    # no splits staging dir required
    assert not (cfg.paths.output_dir / "splits").exists() or not any(
        (cfg.paths.output_dir / "splits").glob("*")
    )
```

- [ ] **Step 2: Run test — expect FAIL (split still called)**

```bash
pytest clio/tests/test_tasks_compress.py::TestRunCompressAll::test_ignores_split_max_min -v
```

- [ ] **Step 3: Minimal compress change**

In `run_compress_all`, replace Phase 1 loop so it **never** calls `split_video`:

```python
    # Phase 1: one compressed file per original (physical split removed — see
    # docs/superpowers/specs/2026-07-18-remove-physical-split-design.md).
    # compress.split_max_min is deprecated and ignored.
    items: list[tuple[Path, Path]] = []
    for video in videos:
        items.append((video, video))
```

Keep `_build_split_info` for now (returns None when source is original). Leave import of `split_video` only if still referenced by tests spy path — prefer removing unused import after tests pass; if removing import breaks spy target, keep `from clio.split import split_video` unused until P4 or re-point spy to a module-level flag. **Preferred:** remove import; test spies `clio.tasks.compress.split_video` only if attribute exists — change test to:

```python
    assert not hasattr(compress_mod, "split_video") or split not called
```

Simplest: leave `from clio.split import split_video` but unused (ruff may flag) — better delete import and change test to only assert output naming / no splits dir:

```python
def test_ignores_split_max_min(...):
    ...
    # do not spy split_video if removed
    records = run_compress_all(cfg)
    assert len(records) == 1
    assert "_seg" not in records[0].compressed_path.stem
```

Also simplify skip fallback that only exists for “split_video failed but segs exist” if it still helps legacy re-runs — **keep** the `orig_to_compressed` skip branch for safety when re-running on legacy trees (spec: do not delete segs; skip path still useful).

- [ ] **Step 4: Run compress tests**

```bash
pytest clio/tests/test_tasks_compress.py -v
```

Expected: PASS (update any tests that assumed split when `split_max_min>0`).

- [ ] **Step 5: Commit**

```bash
git add clio/tasks/compress.py clio/tests/test_tasks_compress.py
git commit -m "feat(compress): stop physical split; always one file per original"
```

---

### Task 3: Analyze window config keys (P2 prep)

**Files:**
- Modify: `clio/config/models.py` (`AnalyzeConfig`)
- Modify: `clio/config/loader.py` (where `AnalyzeConfig(...)` is built)
- Modify: `clio/config/validators.py`
- Modify: `clio/config/descriptions.py`
- Modify: `docs/project.example.yaml`
- Modify: `clio/tests/test_config.py` or `test_config_v2.py` as needed

**Interfaces:**
- Produces on `AnalyzeConfig`:
  - `window_max_min: int = 15`
  - `window_overlap_sec: int = 20`
  - `max_analyze_duration_min: int = 0`  # default change for **new** dataclass only

- [ ] **Step 1: Failing tests**

```python
def test_analyze_window_defaults():
    from clio.config.models import AnalyzeConfig
    a = AnalyzeConfig()
    assert a.window_max_min == 15
    assert a.window_overlap_sec == 20
    assert a.max_analyze_duration_min == 0


def test_analyze_window_loader_keys(tmp_path, ...):
    # write project.yaml with analyze.window_max_min: 10, window_overlap_sec: 30
    # load and assert
```

Follow existing loader test patterns in `clio/tests/test_config_v2.py`.

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

```python
@dataclass
class AnalyzeConfig:
    compressed_subdir: str = "compressed"
    texts_subdir: str = "texts"
    skip_existing: bool = True
    max_analyze_duration_min: int = 0
    window_max_min: int = 15
    window_overlap_sec: int = 20
    max_workers: int = 1
    use_gpmf: bool = False
```

Loader: `raw.get("analyze", {}).get("window_max_min", 15)` etc.

Validators:

```python
_require_min("analyze.window_max_min", config.analyze.window_max_min, 1)
_require_min("analyze.window_overlap_sec", config.analyze.window_overlap_sec, 0)
# overlap must be < window_max*60 — if helper exists use it; else:
if config.analyze.window_overlap_sec >= config.analyze.window_max_min * 60:
    raise ValueError("analyze.window_overlap_sec must be < window_max_min * 60")
```

Descriptions:

```python
"analyze.window_max_min": "AI 分析单窗最长分钟数；超过则临时切片多窗分析后合并",
"analyze.window_overlap_sec": "相邻分析窗重叠秒数，用于边界去重",
"analyze.max_analyze_duration_min": "整片硬顶（分钟），超过则跳过分析。0 不限制。长片主要由 window_max_min 控制",
"compress.split_max_min": "【已废弃】物理分段已移除；此键保留兼容旧配置，压缩阶段忽略",
"compress.splits_subdir": "【已废弃】物理分段已移除",
"compress.reencode_split": "【已废弃】物理分段已移除",
```

`docs/project.example.yaml` analyze section:

```yaml
analyze:
  max_analyze_duration_min: 0
  window_max_min: 15
  window_overlap_sec: 20
```

Keep compress split keys in example with comment `# deprecated, ignored`.

- [ ] **Step 4: pytest config suite PASS**

```bash
pytest clio/tests/test_config.py clio/tests/test_config_v2.py clio/tests/test_config_descriptions.py -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add clio/config docs/project.example.yaml
git commit -m "feat(config): add analyze window_max_min and deprecate compress split"
```

---

### Task 4: Pure window geometry + merge (P2 core lib)

**Files:**
- Create: `clio/analyze_windows.py`
- Create: `clio/tests/test_analyze_windows.py`

**Interfaces:**
- Produces:
  - `dataclass AnalyzeWindow: index: int; start_sec: float; end_sec: float`
  - `build_analyze_windows(duration_sec: float, window_max_min: int, overlap_sec: int) -> list[AnalyzeWindow]`
  - `shift_analysis_times(analysis: dict, offset_sec: float) -> dict`  # deep-copy; shift timeline entries
  - `merge_window_analyses(windows: list[tuple[AnalyzeWindow, dict]], overlap_sec: int) -> dict`
  - Timeline entry keys to shift: any of `start`, `end`, `time`, `t`, `timestamp` if numeric or MM:SS string via existing `_parse_timestamp_sec` from `clio.analyze` (import carefully to avoid cycles — prefer local small parse or import function only).

- [ ] **Step 1: Failing tests**

```python
# clio/tests/test_analyze_windows.py
from clio.analyze_windows import (
    build_analyze_windows,
    merge_window_analyses,
    shift_analysis_times,
)


class TestBuildAnalyzeWindows:
    def test_single_when_short(self):
        ws = build_analyze_windows(600, window_max_min=15, overlap_sec=20)
        assert len(ws) == 1
        assert ws[0].start_sec == 0
        assert ws[0].end_sec == 600

    def test_multi_with_overlap(self):
        # 40 min, 15 min windows, 20s overlap
        ws = build_analyze_windows(2400, window_max_min=15, overlap_sec=20)
        assert len(ws) >= 3
        assert ws[0].start_sec == 0
        assert ws[0].end_sec == 900
        assert ws[1].start_sec == 900 - 20
        assert ws[-1].end_sec == 2400
        # coverage
        assert ws[0].start_sec == 0
        for a, b in zip(ws, ws[1:]):
            assert b.start_sec < a.end_sec  # overlap


class TestShiftAndMerge:
    def test_shift_timeline_numeric(self):
        raw = {"title": "t", "summary": "s", "timeline": [{"start": 10, "end": 20, "text": "a"}]}
        out = shift_analysis_times(raw, 100)
        assert out["timeline"][0]["start"] == 110
        assert out["timeline"][0]["end"] == 120
        assert raw["timeline"][0]["start"] == 10  # no mutate

    def test_merge_prefers_title_window0_and_sorts_timeline(self):
        from clio.analyze_windows import AnalyzeWindow
        w0 = AnalyzeWindow(0, 0, 900)
        w1 = AnalyzeWindow(1, 880, 1800)
        a0 = {"title": "A", "summary": "s0", "timeline": [{"start": 10, "end": 20, "text": "early"}], "highlights": ["h1"], "location": "X"}
        a1 = {"title": "B", "summary": "s1", "timeline": [{"start": 900, "end": 910, "text": "late"}], "highlights": ["h1", "h2"], "location": "Y"}
        merged = merge_window_analyses([(w0, a0), (w1, a1)], overlap_sec=20)
        assert merged["title"] == "A"
        assert "s0" in merged["summary"] and "s1" in merged["summary"]
        assert len(merged["timeline"]) == 2
        assert merged["timeline"][0]["start"] <= merged["timeline"][1]["start"]
        assert set(merged["highlights"]) == {"h1", "h2"}
```

Implement overlap dedupe in merge: if two timeline items both fall in shared overlap region and `abs(start1-start2)<=5` and same `text`/`title` field → keep longer text. Tests may start without strict dedupe assert; add one case:

```python
    def test_merge_dedupes_overlap_near_duplicates(self):
        ...
        # both have event at absolute ~890 with same text
        merged = ...
        assert sum(1 for t in merged["timeline"] if t.get("text") == "dup") == 1
```

- [ ] **Step 2: Run — FAIL**

```bash
pytest clio/tests/test_analyze_windows.py -v
```

- [ ] **Step 3: Implement `clio/analyze_windows.py`**

```python
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalyzeWindow:
    index: int
    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


def build_analyze_windows(
    duration_sec: float,
    window_max_min: int,
    overlap_sec: int,
) -> list[AnalyzeWindow]:
    if duration_sec <= 0:
        return [AnalyzeWindow(0, 0.0, 0.0)]
    window_max = max(1, int(window_max_min)) * 60
    overlap = max(0, int(overlap_sec))
    if overlap >= window_max:
        overlap = max(0, window_max - 1)
    if duration_sec <= window_max:
        return [AnalyzeWindow(0, 0.0, float(duration_sec))]
    step = window_max - overlap
    windows: list[AnalyzeWindow] = []
    start = 0.0
    i = 0
    while start < duration_sec:
        end = min(start + window_max, duration_sec)
        windows.append(AnalyzeWindow(i, float(start), float(end)))
        if end >= duration_sec:
            break
        start += step
        i += 1
        if i > 1000:  # safety
            break
    return windows


_TIME_KEYS = ("start", "end", "time", "t", "timestamp", "cover_timestamp")


def _parse_ts(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    parts = value.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None


def _format_ts(sec: float, original: Any) -> Any:
    if isinstance(original, (int, float)):
        return type(original)(sec) if not isinstance(original, bool) else sec
    # keep MM:SS if original looked like time
    if isinstance(original, str) and ":" in original:
        sec_i = int(round(sec))
        m, s = divmod(sec_i, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    return sec


def shift_analysis_times(analysis: dict, offset_sec: float) -> dict:
    data = copy.deepcopy(analysis)
    if not offset_sec:
        return data

    def shift_obj(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if k in _TIME_KEYS:
                    parsed = _parse_ts(v)
                    if parsed is not None:
                        obj[k] = _format_ts(parsed + offset_sec, v)
                else:
                    shift_obj(v)
        elif isinstance(obj, list):
            for item in obj:
                shift_obj(item)

    shift_obj(data)
    return data


def _timeline_list(analysis: dict) -> list:
    tl = analysis.get("timeline")
    return list(tl) if isinstance(tl, list) else []


def _item_start(item: dict) -> float:
    for k in ("start", "time", "t", "timestamp"):
        if k in item:
            p = _parse_ts(item[k])
            if p is not None:
                return p
    return 0.0


def _item_text(item: dict) -> str:
    for k in ("text", "description", "title", "event"):
        if isinstance(item.get(k), str):
            return item[k]
    return ""


def merge_window_analyses(
    windows: list[tuple[AnalyzeWindow, dict]],
    overlap_sec: int,
) -> dict:
    if not windows:
        return {"title": "", "summary": "", "timeline": []}
    if len(windows) == 1:
        return copy.deepcopy(windows[0][1])

    base = copy.deepcopy(windows[0][1])
    summaries = []
    highlights: list[Any] = []
    locations: list[str] = []
    timeline: list[dict] = []

    for w, raw in windows:
        a = raw
        if isinstance(a.get("summary"), str) and a["summary"]:
            summaries.append(a["summary"])
        if isinstance(a.get("highlights"), list):
            highlights.extend(a["highlights"])
        loc = a.get("location")
        if isinstance(loc, str) and loc and loc != "未知":
            locations.append(loc)
        for item in _timeline_list(a):
            if isinstance(item, dict):
                timeline.append(copy.deepcopy(item))

    # sort
    timeline.sort(key=_item_start)

    # dedupe near-duplicates in time
    deduped: list[dict] = []
    for item in timeline:
        if not deduped:
            deduped.append(item)
            continue
        prev = deduped[-1]
        if abs(_item_start(item) - _item_start(prev)) <= 5 and _item_text(item) == _item_text(prev):
            # keep longer text
            if len(_item_text(item)) > len(_item_text(prev)):
                deduped[-1] = item
            continue
        deduped.append(item)

    base["timeline"] = deduped
    base["summary"] = "\n".join(summaries)
    # unique highlights preserving order
    seen = set()
    uniq_h = []
    for h in highlights:
        key = h if not isinstance(h, dict) else str(h)
        if key in seen:
            continue
        seen.add(key)
        uniq_h.append(h)
    base["highlights"] = uniq_h
    if locations:
        # first non-empty; could join unique
        base["location"] = locations[0] if len(set(locations)) == 1 else " / ".join(dict.fromkeys(locations))
    # title stays from window 0 (base)
    base["analyze_windows"] = [
        {
            "i": w.index,
            "start_sec": w.start_sec,
            "end_sec": w.end_sec,
            "overlap_sec": overlap_sec,
            "status": "ok",
        }
        for w, _ in windows
    ]
    return base
```

- [ ] **Step 4: PASS**

```bash
pytest clio/tests/test_analyze_windows.py -v
```

- [ ] **Step 5: Commit**

```bash
git add clio/analyze_windows.py clio/tests/test_analyze_windows.py
git commit -m "feat(analyze): add window geometry and merge helpers"
```

---

### Task 5: Temp slice helper (P2)

**Files:**
- Modify: `clio/analyze_windows.py`
- Modify: `clio/tests/test_analyze_windows.py`

**Interfaces:**
- Produces:
  - `slice_window_video(*, source: Path, window: AnalyzeWindow, dest_dir: Path, ffmpeg: str, run_ffmpeg=...) -> Path`
  - Uses `run_ffmpeg` from `clio.utils` (injectable for tests)
  - Naming: `{source.stem}_w{index:02d}_{int(start)}-{int(end)}.mp4`
  - Prefer copy args: `["-ss", str(start), "-i", str(source), "-t", str(dur), "-c", "copy", "-y", str(out)]`
  - `cleanup_analyze_windows_dir(dest_dir: Path) -> None` — delete `*_w*.mp4` orphans

- [ ] **Step 1: Test with mock run_ffmpeg**

```python
def test_slice_window_video_invokes_ffmpeg(tmp_path, monkeypatch):
    src = tmp_path / "001_GL.mp4"
    src.write_bytes(b"\x00" * 10)
    dest = tmp_path / ".analyze_windows"
    calls = []

    def fake_run(args, ffmpeg, **kw):
        calls.append(args)
        # last arg is output path
        Path(args[-1]).write_bytes(b"x")

    from clio.analyze_windows import AnalyzeWindow, slice_window_video
    out = slice_window_video(
        source=src,
        window=AnalyzeWindow(0, 0, 60),
        dest_dir=dest,
        ffmpeg="ffmpeg",
        run_ffmpeg=fake_run,
    )
    assert out.is_file()
    assert "w00" in out.name
    assert any("-ss" in str(a) or a == "-ss" for a in calls[0])
```

- [ ] **Step 2–4: Implement + pass + commit**

```bash
git commit -m "feat(analyze): temp ffmpeg slice for analyze windows"
```

---

### Task 6: Wire analyze_with_windows into task (P2)

**Files:**
- Modify: `clio/tasks/analyze.py` (`_analyze_one` / equivalent single-file path)
- Modify: `clio/tests/test_tasks_analyze.py`

**Interfaces:**
- Consumes: `is_legacy_split_path`, `build_analyze_windows`, `slice_window_video`, `shift_analysis_times`, `merge_window_analyses`, existing `analyze_video` from `clio.analyze`
- Behavior:
  1. If `is_legacy_split_path(compressed)` → keep current single `analyze_video(compressed)` path.
  2. Else:
     - whole-clip hard cap: if `max_analyze_duration_min > 0` and duration > cap → skip (unchanged).
     - `windows = build_analyze_windows(duration, window_max_min, window_overlap_sec)`
     - if single window: call `analyze_video` on full compressed (no slice required) OR slice full — prefer **no slice** for single window (faster).
     - if multi: for each window, slice → `analyze_video(str(slice_path))` → `shift_analysis_times(..., window.start_sec)` → collect; on any exception mark fail; always delete slice in `finally`; if any fail → return None **without** writing texts.
     - merge → write texts once with `analyze_windows` metadata.
  3. `dest_dir = config.paths.output_dir / ".analyze_windows"`

- [ ] **Step 1: Failing integration-style unit test**

```python
def test_multi_window_merges_and_writes_one_json(monkeypatch, tmp_path, cfg_fixture):
    # compressed duration 2400s, window 15, overlap 20
    # mock analyze_video to return timeline with local start=5
    # assert one json written, timeline starts near 5 and 5+880, etc.
    # assert analyze_windows len >= 2

def test_window_failure_writes_nothing(monkeypatch, tmp_path, cfg_fixture):
    # second window raises → no texts json
```

Reuse fixtures from `test_tasks_analyze.py` (`_cfg` patterns). Mock `get_duration_sec`, `analyze_video`, `slice_window_video` / `run_ffmpeg`.

- [ ] **Step 2: Run FAIL**

- [ ] **Step 3: Implement branch in `_analyze_one` (or whatever the per-clip function is named — currently the body around `analyze_video(` at `clio/tasks/analyze.py:164`)**

Pseudocode structure (fit real function signature):

```python
from clio.identity import is_legacy_split_path
from clio.analyze_windows import (
    build_analyze_windows,
    cleanup_analyze_windows_dir,
    merge_window_analyses,
    shift_analysis_times,
    slice_window_video,
)

# after duration gate...
if is_legacy_split_path(compressed):
    analysis = analyze_video(str(compressed), config, ...)
else:
    w_max = int(getattr(config.analyze, "window_max_min", 15) or 15)
    overlap = int(getattr(config.analyze, "window_overlap_sec", 20) or 0)
    windows = build_analyze_windows(duration_sec, w_max, overlap)
    if len(windows) == 1:
        analysis = analyze_video(str(compressed), config, ...)
        analysis = shift_analysis_times(analysis, 0)  # no-op
        analysis["analyze_windows"] = [{
            "i": 0, "start_sec": 0, "end_sec": duration_sec,
            "overlap_sec": overlap, "status": "ok",
        }]
    else:
        ffmpeg = resolve_binary(config.paths.ffmpeg, "ffmpeg")
        dest = config.paths.output_dir / ".analyze_windows"
        dest.mkdir(parents=True, exist_ok=True)
        partials = []
        try:
            for w in windows:
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("分析被用户取消")
                slice_path = slice_window_video(
                    source=compressed, window=w, dest_dir=dest, ffmpeg=ffmpeg
                )
                try:
                    part = analyze_video(str(slice_path), config, ...)
                    part = shift_analysis_times(part, w.start_sec)
                    partials.append((w, part))
                finally:
                    slice_path.unlink(missing_ok=True)
        except Exception as e:
            # fail closed
            print(...)
            state.mark(..., "error")
            return None
        analysis = merge_window_analyses(partials, overlap)
```

Ensure existing write path (`media_identity`, `_write_text_file`, `write_json_atomic`) unchanged after `analysis` is ready.

- [ ] **Step 4: Run analyze tests**

```bash
pytest clio/tests/test_tasks_analyze.py clio/tests/test_analyze_windows.py -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add clio/tasks/analyze.py clio/tests/test_tasks_analyze.py clio/analyze_windows.py
git commit -m "feat(analyze): multi-window Gemini analyze with fail-closed merge"
```

---

### Task 7: Cut + JianYing use legacy offset helper (P3a)

**Files:**
- Modify: `clio/tasks/cut.py` (where offset is applied ~312–322)
- Modify: `clio/export/jianying.py` (`_build_index_to_offset` / apply)
- Modify: related tests if assertions need `is_legacy_*`

**Interfaces:**
- Consumes: `legacy_segment_offset_sec`, `load_identity` / `resolve_identity`
- Formula: `offset = legacy_segment_offset_sec(identity)`

- [ ] **Step 1:** Add/adjust unit test: non-legacy identity with accidental non-zero field still… actually new writes zero offset; test that helper forces 0 when `segment_index is None` and stem plain.

Existing cut tests with seg fixtures must still pass.

- [ ] **Step 2–4:** Replace direct `identity.segment_offset_sec` reads used for **applying** cut/export offsets with `legacy_segment_offset_sec(identity)`. Do **not** strip storage of offsets on legacy artifacts.

```bash
pytest clio/tests/test_tasks_cut.py clio/tests/test_export.py -v --tb=short
git commit -m "refactor(cut,export): apply segment offset only for legacy split"
```

---

### Task 8: Config UI labels + optional .gitignore (P3b)

**Files:**
- Modify: `clio/ui/static/src/editor-config.js` labels map
- Modify: `.gitignore` if project ignores output caches — add `.analyze_windows/` under output patterns if appropriate
- Check `clio/ui/routes/config_routes.py` / field ownership lists include new analyze keys (project layer)

- [ ] **Step 1–4:**

```javascript
'analyze.window_max_min': '分析窗长（分钟）',
'analyze.window_overlap_sec': '分析窗重叠（秒）',
'analyze.max_analyze_duration_min': '整片分析硬顶（分钟，0=不限制）',
'compress.split_max_min': '【废弃】物理分段阈值',
```

If vitest covers label map, update.

```bash
# if frontend tests exist for config labels
npm test -- --run editor-config  # only if project has this script; else skip
```

```bash
git commit -m "feat(ui): config labels for analyze windows; deprecate split knobs"
```

---

### Task 9: Docs + ROADMAP (P3c)

**Files:**
- Modify: `README.md`, `README.en.md` (auto-split product line → analyze windows)
- Modify: `ROADMAP.md` — add R-029 (or next free id) linking the design + plan; mark P0–P2 done when commits land
- Modify: `docs/cli-reference.md` if it documents `split_max_min` behavior

- [ ] **Step 1:** Edit product copy only (no code).

- [ ] **Step 2: Commit**

```bash
git commit -m "docs: document analyze windows; deprecate physical split"
```

---

### Task 10: Full regression pass

- [ ] **Step 1: Run full unit suite**

```bash
pytest clio/tests -q --tb=line
```

Expected: all pass. Fix any fallout from default `max_analyze_duration_min=0` or compress split removal.

- [ ] **Step 2: Manual smoke (if ffmpeg + keys available)**  
  Short clip: compress → analyze (single window).  
  Optional: long compressed mock duration with mocked AI already covered by tests.

- [ ] **Step 3: Final commit only if fixes needed; otherwise stop.**  
  Ask user before `git push`.

---

## Spec coverage checklist

| Spec section | Task |
| --- | --- |
| Goals / non-goals | Tasks 1–6 enforce; non-goals not implemented |
| Legacy gate | Task 1 |
| Compress no split | Task 2 |
| Config window_* + deprecate split | Task 3, 8, 9 |
| Window geometry + merge | Task 4 |
| Temp ffmpeg slice | Task 5 |
| Analyze wire + fail-closed | Task 6 |
| Absolute timeline + single texts | Task 6 |
| Cut/export offset | Task 7 |
| UI labels | Task 8 |
| Docs | Task 9 |
| P4 dead-code delete | **Out of this plan** (optional later) |
| Transcribe “prefer one original” | Soft: works naturally without segs; deep rewrite deferred unless tests fail |
| UI multi-row legacy keep | No change required in this plan (legacy paths untouched) |

## Out of plan (explicit)

- P4 delete `clio/split.py` write path and shrink legacy tests
- Auto-migrate command
- Gemini native offsets
- Partial window success
- Scene-based windows
