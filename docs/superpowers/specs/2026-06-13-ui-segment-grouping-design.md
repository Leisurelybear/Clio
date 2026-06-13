# R-013a: Compressed View Segment Grouping — Technical Design

> **Status:** Draft
> **Date:** 2026-06-13
> **Related:** Video splitting integration (split.py + compress Phase 1/2)

## 1. Overview

After implementing video splitting (long source → N × `_segNN` compressed files),
the compressed view in the sidebar shows one flat list with entries like:

```
[001] GL010683_seg01   [analyze] [voiceover]
[002] GL010683_seg02   [analyze] [voiceover]
[003] GL020735_铁塔     [analyze] [voiceover]
```

This is confusing — segments of the same video are scattered by their index
prefix, not visually grouped. The user has no sense of "these 2 segments belong
to GL010683."

**Goals:**
- Segment files (`_segNN`) are visually grouped under their parent original name
- Non-segmented files render unchanged (current flat behavior)
- Original view shows a badge if segments exist
- Toggle behavior (click to play segment, dropdown per segment) stays identical

> **Note:** The video-splitting step (`split.py` + compress Phase 1/2) is already
> implemented on this branch. This doc is purely additive to the existing flat-list
> code and degrades gracefully (§3.5) when no `_seg` files exist.

## 2. 方案 A: Backend matching fix (prerequisite)

**File:** `vlog_tool/ui/services/file_service.py`

### `_find_original_for_compressed`

Current logic matches `stem.split("_", 1)[1]` against input_dir filenames.
For `001_GL010683_seg01`, suffix = `GL010683_seg01` — no match.

**Fix:** After direct match fails, check `_seg\d+` suffix and retry with base.

```python
import re

# After failed direct match:
m = re.match(r"^(.+)_seg\d+$", suffix)
if m:
    base = m.group(1)
    for p in input_dir.iterdir():
        if p.is_file() and p.stem.lower() == base:
            return p.name
```

**Impact:** The original filename resolves to `GL010683.MP4` instead of `None`.
This cascades to the `"orig": ...` field in `/api/videos` and the "match" dot
indicator in the UI. Without this fix, segments show as "no match" even though
they were properly split from the original.

### `_find_compressed_for_original`

Current logic does exact match `rest.lower() == needle`. For segments,
`rest` = `GL010683_seg01`, `needle` = `gl010683` — no match.

**Fix:** After exact match fails, collect files where `rest.lower()` starts with
`needle + "_seg"`.

```python
# After direct match fails:
matches = []
for p in comp_dir.iterdir():
    if p.suffix.lower() not in VIDEO_EXTS or "_" not in p.stem:
        continue
    idx, rest = p.stem.split("_", 1)
    if rest.lower().startswith(needle + "_seg"):
        matches.append((p.name, idx))
matches.sort(key=lambda m: m[1])  # sort by index
return matches or None
```

**Return type change:** `_find_compressed_for_original` now returns
`list[tuple[str, str]] | None` (all matching segments, sorted by index)
instead of a single `(name, idx)` tuple. **This is a breaking change for
`handle_get_videos`'s original-view branch**, which currently does:

```python
comp = _find_compressed_for_original(p.stem, comp_dir)
idx = comp[1] if comp else None
...
"match": ({"source": "compressed", "file": comp[0], "index": comp[1]} if comp else None),
```

For a single-match original (non-split, the common case), `comp` is now
`[(name, idx)]` — update to `comp[0]` before indexing:

```python
comp = _find_compressed_for_original(p.stem, comp_dir)
first = comp[0] if comp else None
idx = first[1] if first else None
...
"match": ({"source": "compressed", "file": first[0], "index": first[1]} if first else None),
"segment_matches": [{"file": f, "index": i} for f, i in comp] if comp and len(comp) > 1 else None,
```

**Impact:** Original view shows a match for files that were split. When an
original was split into multiple segments, `segment_matches` carries all of
them (for the badge / future "jump to segment" UI), while `match` still
points at segment 1 for backward compatibility with existing click/playback
logic.

## 3. 方案 B: UI Tree Grouping

### 3.1 Backend — `/api/videos` response extension

**File:** `vlog_tool/ui/routes/videos.py` → `handle_get_videos()`

#### Response shape (additions in bold):

```json
{
  "videos": [
    {
      "file": "001_GL010683_seg01.mp4",
      "index": "001",
      "source": "compressed",
      "match": true,
      "orig": "GL010683.MP4",
      "text_json": null,
      "script_json": null,
      "duration": 120.5,
      **"group_key": "GL010683",**
      **"segment_label": "1/2"**
    }
  ],
  **"groups": {**
    **"GL010683": {**
      **"original_stem": "GL010683",**
      **"indices": ["001", "002"],**
      **"total": 2**
    **}**
  **}**
}
```

#### Backend algorithm (two-pass):

```
Pass 1: build flat video list + group_members dict
  for each compressed file:
    extract stem, strip index prefix → suffix
    if suffix matches ^(.+)_seg(\d+)$:
      group_key = m.group(1)
      seg_num = int(m.group(2))
      video dict += { group_key, segment_label: "N/total" (placeholder) }
      group_members[group_key].append((idx, seg_num))
    else:
      video dict += { group_key: None, segment_label: None }

Pass 2: compute totals, fill labels
  groups = {}
  for group_key, members in group_members.items():
    members.sort(key=lambda x: x[1])  # sort by seg_num
    total = len(members)
    groups[group_key] = {
      "original_stem": group_key,
      "indices": [m[0] for m in members],
      "total": total
    }
    for idx, seg_num in members:
      v = find_video_by_index(videos, idx)
      v["segment_label"] = f"{seg_num}/{total}"

Response = { "videos": videos, "groups": groups }
```

#### Parsing regex:

```python
_SEG_RE = re.compile(r"^(.+)_seg(\d+)$")

def _parse_segment_info(stem: str) -> tuple[str | None, int | None]:
    """Returns (group_key, segment_number) or (None, None)."""
    if "_" not in stem:
        return None, None
    m = _SEG_RE.match(stem.split("_", 1)[1])
    if not m:
        return None, None
    return m.group(1), int(m.group(2))
```

### 3.2 Frontend — sidebar.js

**File:** `vlog_tool/ui/static/src/sidebar.js`

#### `renderVideoList()` refactoring

Current: single flat loop over `state.videos`.
New: two phases — group phase + ungrouped phase.

**Pseudo:**

```javascript
function renderVideoList() {
  const ul = $('video-list');
  ul.innerHTML = '';

  const grouped = state.videos.filter(v => v.group_key);
  const ungrouped = state.videos.filter(v => !v.group_key);

  // --- 1. Grouped section ---
  // Build group map from group_key -> videos[]
  const groups = {};
  for (const v of grouped) {
    (groups[v.group_key] ??= []).push(v);
  }

  for (const [key, items] of Object.entries(groups)) {
    // Group header row (clickable, expand/collapse)
    const header = createGroupHeader(key, items.length);
    ul.appendChild(header);
    // Child list (toggle display with nextElementSibling)
    const childUl = document.createElement('ul');
    childUl.className = 'video-group-children';
    for (const v of items) {
      childUl.appendChild(renderVideoItem(v));
    }
    ul.appendChild(childUl);
  }

  // --- 2. Ungrouped section ---
  for (const v of ungrouped) {
    ul.appendChild(renderVideoItem(v));
  }
}
```

#### `renderVideoItem()` extraction

Extract existing item-rendering logic into a standalone function:

```javascript
function renderVideoItem(v) {
  const li = document.createElement('li');
  li.className = 'video-item';
  // ... existing logic: active class, no-match class, display name,
  //     status icons, dropdown, click handler ...
  return li;
}
```

The display name for segment items should show `seg N/total`:

```javascript
// Inside renderVideoItem:
let displayName = v.file.replace(/^\d+_/, '');
if (v.segment_label) {
  displayName = displayName.replace(/_seg\d+$/i, '') + ` [seg ${v.segment_label}]`;
}
```

This fallback ensures segment items rendered outside a group (e.g. original
view, or if `state.expandedGroups` rendering falls back to flat list) never
show the raw `_seg01` suffix.

Actually, in group view, the header already shows the original name, so child
items can be concise:

```
▶ GL010683 (2 段)
  [001] seg 1/2  [analyze] [voiceover]
  [002] seg 2/2  [analyze] [voiceover]
```

Use `v.segment_label` for the display instead of the raw `_seg01` suffix.

#### State persistence for expand/collapse

```javascript
// Simple: store expanded keys in state
state.expandedGroups ??= {};
// In group header click:
state.expandedGroups[groupKey] = !state.expandedGroups[groupKey];
renderVideoList();  // re-render
```

On render, `childUl.style.display` = `state.expandedGroups[key] ? '' : 'none'`.

### 3.3 State — state.js

**File:** `vlog_tool/ui/static/src/state.js`

**No new fields needed for API response** — `state.videos[].group_key` and
`state.groups` are populated from API data directly.

Add optional expand/collapse tracking:

```javascript
function defaultState() {
  return {
    videos: [],
    groups: {},           // from API, keyed by original_stem
    expandedGroups: {},   // UI-only, keyed by group_key
    // ... existing fields ...
  };
}
```

### 3.4 CSS — style.css

**File:** `vlog_tool/ui/static/style.css`

New classes:

```css
.video-group-header {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  cursor: pointer;
  font-weight: 500;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
  user-select: none;
}
.video-group-header:hover {
  background: var(--bg-hover);
}
.group-toggle {
  font-size: 10px;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
  color: var(--text-tertiary);
}
.video-group-children {
  list-style: none;
  margin: 0;
  padding: 0;
}
.video-group-children .video-item {
  padding-left: 22px;
}
.group-count-badge {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin: 0 2px;
}
```

### 3.5 Edge Cases

#### No segments, only ungrouped videos

`state.groups` is empty → grouped phase produces zero output → flat list
identical to current UI. No visual difference.

#### Mixed groups + ungrouped

Groups render first (sorted by group_key), then ungrouped videos. The division
makes it clear which are segments and which are independent clips.

#### Single segment group

Should not happen with `split_max_min > 0` (a video shorter than threshold
won't be split), but handle gracefully: render as a group with 1 child.

#### Original view (source="original")

- No `group_key`/`groups` (these are only set for compressed view)
- Flat list, unchanged
- Each original file shows match indicator (already handled by 方案 A)

#### Plan tab click

Plan clips reference `"index": "001"`. The playback logic already looks up the
compressed file by index — no change needed. Index assignment is per-segment
after splitting, so each segment has a unique index.

#### Source toggle

- Switch to original → `renderVideoList()` called with `state.source='original'`
  → API returns `groups: {}` → flat list
- Switch back to compressed → `renderVideoList()` called again → groups restored
- Expand/collapse state in `state.expandedGroups` persists across toggles

#### Dropdown menus on grouped items

Each segment is still a separate `.video-item` with its own dropdown
(analyze/voiceover/refine). The group header has no dropdown — click toggles
expand/collapse, not video selection.

#### After analysis (titles render)

Existing logic in `renderVideoItem` uses `v.text_json?.title` to replace
filename. For segments, titles like "卢浮宫入口 (Part 1)" make segments
meaningful even without the visual group. The grouping just provides structural
clarity.

## 4. Implementation Order

1. **方案 A** — `_find_original_for_compressed` + `_find_compressed_for_original`
   (~10 lines each, ~15 minutes)
2. **方案 B backend** — `handle_get_videos` group construction in `routes/videos.py`
   (~40 lines, ~20 minutes)
3. **方案 B CSS** — new group classes in `style.css`
   (~25 lines, ~10 minutes)
4. **方案 B frontend** — `renderVideoList` refactor in `sidebar.js`
   (~60 lines including `renderVideoItem` extraction, ~30 minutes)
5. **方案 B state** — optional `expandedGroups` in `state.js`
   (~3 lines, ~5 minutes)
6. **Verification** — serve and visually confirm grouping works
   (~15 minutes)

**Total est.:** ~95 minutes

## 5. Files Modified

| File | Change |
|------|--------|
| `vlog_tool/ui/services/file_service.py` | `_find_original_for_compressed` + `_find_compressed_for_original` seg matching |
| `vlog_tool/ui/routes/videos.py` | `handle_get_videos` two-pass group construction |
| `vlog_tool/ui/static/src/sidebar.js` | `renderVideoList` → group section + `renderVideoItem` extraction |
| `vlog_tool/ui/static/src/state.js` | Optional `expandedGroups` field |
| `vlog_tool/ui/static/style.css` | `.video-group-header`, `.group-toggle`, `.video-group-children`, `.group-count-badge` |

No new files created. No dependencies added.
