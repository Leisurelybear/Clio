# N-01: JianYing Draft Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a ready-to-open JianYing Pro (剪映专业版) draft from `plan.json` output.

**Architecture:** New `vlog_tool/export/` package with `FORMAT_REGISTRY` and `jianying.py` core builder. CLI + UI entry points.

**Tech Stack:** Python 3.11+, stdlib only (json, uuid, pathlib, datetime). No external dependencies.

---

## File Structure

| File | Responsibility |
|---|---|
| `vlog_tool/export/__init__.py` | `FORMAT_REGISTRY`, `export_plan()` dispatch |
| `vlog_tool/export/jianying.py` | `export_plan_to_jianying()`, material resolution, track building |
| `main.py` | CLI `export` subcommand |
| `vlog_tool/ui/routes/export.py` | `handle_post_export()` API route |
| `vlog_tool/ui/server.py` | Register POST route |
| `vlog_tool/ui/static/src/editor.js` | "导出到剪映" button in plan view |

### Task 1: `vlog_tool/export/__init__.py` — Format Registry

- [ ] **Create `vlog_tool/export/__init__.py`**

```python
"""Video editing software draft export."""

from __future__ import annotations

from pathlib import Path


FORMAT_REGISTRY: dict[str, type] = {}


def export_plan(
    format: str,
    plan_path: Path,
    output_dir: Path,
    input_dir: Path,
    day_label: str = "day1",
    **kwargs,
) -> Path:
    """Export plan to the specified format.

    Returns path to the output draft directory.
    """
    exporter = FORMAT_REGISTRY.get(format)
    if exporter is None:
        raise ValueError(f"Unknown export format: {format}. Available: {list(FORMAT_REGISTRY)}")
    return exporter(plan_path, output_dir, input_dir, day_label, **kwargs)
```

- [ ] **Commit**

```bash
git add vlog_tool/export/__init__.py
git commit -m "feat(export): add format registry skeleton"
```

### Task 2: `vlog_tool/export/jianying.py` — Core Draft Builder

This is the main task. It generates `draft_content.json` in JianYing Pro 5.9 format (plain JSON, unencrypted).

**Helper functions:**
- `_resolve_video(index, input_dir)` → `(Path, duration_us)` or `None`
- `_to_microseconds(seconds: float)` → `int`
- `_build_materials(plan_data, input_dir)` → `(materials_dict, index_to_material_id)`
- `_build_tracks(plan_data, index_to_material_id)` → `tracks_list`
- `export_plan_to_jianying(plan_path, output_dir, input_dir, day_label)` → `Path`

- [ ] **Create `vlog_tool/export/jianying.py`**

```python
"""JianYing Pro (剪映专业版) draft export.

Generates draft_content.json from plan.json output.
Target format: JianYing 5.9 (plain JSON, unencrypted).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from vlog_tool.cut import parse_time_range
from vlog_tool.utils import find_videos, get_duration_sec


def _to_microseconds(seconds: float) -> int:
    return int(seconds * 1_000_000)


def _resolve_video(
    index: str,
    input_dir: Path,
    ffprobe: str | None = None,
) -> tuple[Path, int] | None:
    """Find original video by index (e.g. '001' → '001_GL010683.mp4').

    Returns (absolute_path, duration_us) or None if not found.
    """
    videos = find_videos(input_dir, recursive=True)
    pattern = f"{index}_"
    for v in videos:
        if v.stem.startswith(pattern):
            if ffprobe is None:
                return None
            try:
                duration = get_duration_sec(v, ffprobe)
            except Exception:
                return None
            return v.resolve(), _to_microseconds(duration)
    return None


def _build_materials(
    plan_data: dict,
    input_dir: Path,
    ffprobe: str | None = None,
) -> tuple[dict, dict[str, str]]:
    """Build materials.videos and materials.texts.

    Returns (materials_dict, index_to_material_id).
    """
    videos: list[dict] = []
    texts: list[dict] = []
    index_to_material_id: dict[str, str] = {}
    seen_indices: set[str] = set()

    for seg in plan_data.get("sequence", []):
        idx = seg.get("index", "")
        if not idx:
            continue

        # Video material (one per unique index)
        if idx not in seen_indices:
            seen_indices.add(idx)
            resolved = _resolve_video(idx, input_dir, ffprobe)
            if resolved is None:
                print(f"  [跳过] 视频素材 [{idx}] 未找到，跳过相关片段")
                continue
            vid_path, duration_us = resolved
            mat_id = str(uuid.uuid4())
            index_to_material_id[idx] = mat_id
            videos.append({
                "id": mat_id,
                "type": "video",
                "path": str(vid_path),
                "duration": duration_us,
            })

        # Text material (one per sequence entry)
        voiceover = (seg.get("voiceover_hint") or "").strip()
        if voiceover:
            text_id = str(uuid.uuid4())
            content = {
                "text": voiceover,
                "font_color": "#FFFFFF",
                "font_size": 18,
                "bold": False,
            }
            texts.append({
                "id": text_id,
                "content": json.dumps(content, ensure_ascii=False),
            })
            # Store text material id keyed by sequence index
            seg["_text_material_id"] = text_id

    return {
        "videos": videos,
        "texts": texts,
        "audios": [],
        "stickers": [],
        "video_effects": [],
        "material_animations": [],
        "transitions": [],
        "masks": [],
        "common_masks": [],
        "canvases": [],
        "speeds": [],
        "audio_fades": [],
        "placeholder_infos": [],
        "vocal_separations": [],
    }, index_to_material_id


def _build_tracks(
    plan_data: dict,
    index_to_material_id: dict[str, str],
) -> list[dict]:
    """Build video and text tracks from plan sequence."""
    video_segments: list[dict] = []
    text_segments: list[dict] = []
    accumulated_us = 0
    skipped_count = 0

    for seg in plan_data.get("sequence", []):
        idx = seg.get("index", "")
        if idx not in index_to_material_id:
            skipped_count += 1
            continue

        timeline_str = (seg.get("use_timeline") or "").strip()
        try:
            start_sec, end_sec = parse_time_range(timeline_str)
        except (ValueError, TypeError):
            skipped_count += 1
            print(f"  [跳过] 片段 [{idx}] 时间格式无效: {timeline_str}")
            continue

        duration_us = _to_microseconds(end_sec - start_sec)
        if duration_us <= 0:
            skipped_count += 1
            print(f"  [跳过] 片段 [{idx}] 时长为 0: {timeline_str}")
            continue

        material_id = index_to_material_id[idx]
        seg_uuid = str(uuid.uuid4())

        video_segments.append({
            "id": seg_uuid,
            "material_id": material_id,
            "target_timerange": {
                "start": accumulated_us,
                "duration": duration_us,
            },
            "source_timerange": {
                "start": _to_microseconds(start_sec),
                "duration": duration_us,
            },
        })

        # Text segment for voiceover
        text_mat_id = seg.get("_text_material_id")
        if text_mat_id:
            text_segments.append({
                "id": str(uuid.uuid4()),
                "material_id": text_mat_id,
                "target_timerange": {
                    "start": accumulated_us,
                    "duration": duration_us,
                },
            })

        accumulated_us += duration_us

    tracks = []
    if video_segments:
        tracks.append({
            "id": str(uuid.uuid4()),
            "type": "video",
            "segments": video_segments,
        })
    if text_segments:
        tracks.append({
            "id": str(uuid.uuid4()),
            "type": "text",
            "segments": text_segments,
        })

    if skipped_count:
        print(f"  [导出] {skipped_count} 个片段因素材缺失或时间格式错误被跳过")

    return tracks


def export_plan_to_jianying(
    plan_path: Path,
    output_dir: Path,
    input_dir: Path,
    day_label: str = "day1",
    ffprobe: str | None = None,
) -> Path:
    """Generate JianYing draft from plan JSON.

    Returns path to the output draft directory.
    """
    if not plan_path.is_file():
        raise FileNotFoundError(f"plan 文件不存在: {plan_path}")

    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    sequence = plan_data.get("sequence", [])
    if not sequence:
        print(f"  [警告] plan 文件为空序列: {plan_path}")

    materials, index_to_material_id = _build_materials(plan_data, input_dir, ffprobe)
    tracks = _build_tracks(plan_data, index_to_material_id)

    total_duration_us = 0
    for track in tracks:
        for seg in track.get("segments", []):
            seg_end = seg["target_timerange"]["start"] + seg["target_timerange"]["duration"]
            if seg_end > total_duration_us:
                total_duration_us = seg_end

    draft = {
        "id": str(uuid.uuid4()),
        "name": plan_data.get("day_title", day_label),
        "duration": total_duration_us,
        "fps": 30,
        "canvas_config": {
            "width": 1920,
            "height": 1080,
            "ratio": 1.7777777777777777,
        },
        "platform": {
            "app_source": "lv",
            "app_version": "5.9.0",
            "os": "windows",
        },
        "materials": materials,
        "tracks": tracks,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    draft_path = output_dir / "draft_content.json"
    draft_path.write_text(
        json.dumps(draft, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  [导出] JianYing 草稿已生成: {output_dir}")
    print(f"  [导出] 共 {len(sequence)} 个片段，{len(materials['videos'])} 个视频素材，{total_duration_us / 1_000_000:.1f} 秒")

    return output_dir
```

- [ ] **Register in `__init__.py`**

```python
from vlog_tool.export.jianying import export_plan_to_jianying

FORMAT_REGISTRY["jianying"] = export_plan_to_jianying
```

- [ ] **Commit**

```bash
git add vlog_tool/export/jianying.py vlog_tool/export/__init__.py
git commit -m "feat(export): add JianYing draft_content.json builder"
```

### Task 3: CLI `export` Subcommand

- [x] **Add `export` subcommand in `main.py`** (after `p_tokens`, before `p_transcribe`)

```python
p_export = sub.add_parser("export", help="导出 plan 到剪辑软件草稿")
p_export.add_argument("--format", default="jianying", choices=["jianying"], help="导出格式")
p_export.add_argument("--day", default="day1", help="日 vlog 标签（默认 day1）")
p_export.add_argument("--output", type=Path, default=None, help="输出目录（默认 output/export/<day>_<format>/）")
```

- [x] **Add handler** (after the `elif args.command == "tokens":` block, before `except`)

```python
elif args.command == "export":
    from vlog_tool.export import export_plan

    plan_path = config.plans_dir / f"{args.day}_plan.json"
    out_dir = args.output or config.paths.output_dir / "export" / f"{args.day}_{args.format}"
    ffprobe = config.paths.ffprobe
    export_plan(args.format, plan_path, out_dir, config.paths.input_dir, args.day, ffprobe=ffprobe)
    return 0
```

- [x] **Commit**

```bash
git add main.py
git commit -m "feat(cli): add export subcommand for JianYing draft generation"
```

### Task 4: UI API Route

- [x] **Create `vlog_tool/ui/routes/export.py`**

```python
"""Export routes for plan to video editing software drafts."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

from vlog_tool.export import export_plan


def handle_post_export(
    handler: BaseHTTPRequestHandler,
    qs: dict[str, list[str]],
    obj: dict,
) -> None:
    """POST /api/export — export plan to JianYing draft."""
    day = obj.get("day", "day1")
    fmt = obj.get("format", "jianying")

    proj_input = handler._resolve_project_input(qs)
    cfg = handler._get_config(proj_input)

    plan_path = cfg.plans_dir / f"{day}_plan.json"
    if not plan_path.is_file():
        handler._send_json({"ok": False, "error": f"plan 文件不存在: {plan_path}"}, 404)
        return

    out_dir = cfg.paths.output_dir / "export" / f"{day}_{fmt}"
    try:
        result_path = export_plan(fmt, plan_path, out_dir, cfg.paths.input_dir, day, ffprobe=cfg.paths.ffprobe)
    except (FileNotFoundError, ValueError) as e:
        handler._send_json({"ok": False, "error": str(e)}, 400)
        return

    handler._send_json({"ok": True, "path": str(result_path)})
```

- [x] **Register in `server.py`**

Add import:
```python
from vlog_tool.ui.routes.export import handle_post_export
```

Add route in `do_POST`:
```python
if path == "/api/export":
    return handle_post_export(self, qs, obj)
```

- [x] **Commit**

```bash
git add vlog_tool/ui/routes/export.py vlog_tool/ui/server.py
git commit -m "feat(ui): add POST /api/export route for JianYing draft"
```

### Task 5: UI Frontend — "导出到剪映" Button

- [x] **Add button in `renderPlan()`** in `vlog_tool/ui/static/src/editor.js`

After the "裁剪此分集" section, add an "导出到剪映" button:

```javascript
// ── 导出区块 ──
const exportSection = document.createElement('div');
exportSection.className = 'cut-section';
exportSection.style.marginTop = '16px';
exportSection.innerHTML = `
  <h3>导出到剪映</h3>
  <p class="hint">生成剪映专业版可直接打开的草稿文件</p>
  <button id="btn-jianying-export" class="btn-primary">${icon('export', 16)} 导出到剪映</button>
  <div id="export-result" style="margin-top:8px"></div>
`;
pane.appendChild(exportSection);
```

Add event handler after the cut section event handler:

```javascript
$('btn-jianying-export')?.addEventListener('click', async () => {
  const resultDiv = $('export-result');
  resultDiv.innerHTML = '<span class="muted">导出中…</span>';
  try {
    const r = await api('POST', '/api/export', { day: state.currentDay || 'day1', format: 'jianying' });
    if (r.ok) {
      resultDiv.innerHTML = `<span style="color:var(--ok,#484)">✓ 已导出到 ${escapeHtml(r.path)}</span>`;
    } else {
      resultDiv.innerHTML = `<span style="color:var(--err,#c44)">✗ ${escapeHtml(r.error || '导出失败')}</span>`;
    }
  } catch (e) {
    resultDiv.innerHTML = `<span style="color:var(--err,#c44)">✗ 导出失败: ${escapeHtml(e.message)}</span>`;
  }
});
```

Add `export` icon to the icon set (find existing `icon()` function):

```python
# In api.js icon map, add:
# export: '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
```

- [x] **Commit**

```bash
git add vlog_tool/ui/static/src/editor.js
git commit -m "feat(ui): add JianYing export button to plan view"
```

---

## Post-Implementation

1. `python main.py check` — environment check
2. `ruff format . && ruff check .` — lint
3. `python main.py export --day day1` — manual smoke test (requires existing plan)
4. Verify `output/export/day1_jianying/draft_content.json` is valid JSON with correct structure
5. `python -m pytest vlog_tool/tests/ -v` — existing tests still pass
