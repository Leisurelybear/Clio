# Design: Plan Domain Model, Structural Edit & Export Readiness

**Date**: 2026-07-17  
**Status**: Implemented on `main` (incl. playhead + insert follow-up; per-segment AI regenerate declined)  
**Route**: A — “剪辑师一天流” (plan edit + export checklist)  
**Approach**: Domain model foundation (approach 3), incremental adoption

## 1. Goals and non-goals

### Goals (this iteration)

1. **Plan domain model**: `Plan` / `PlanSegment` with clear load/dump boundaries and unknown-field preservation.
2. **Structural editing in UI**: drag-reorder, delete segment, edit `use_timeline` / `title` (plus existing `reason` / `voiceover_hint`).
3. **Save validation**: `PUT /api/plan` goes through the domain layer; reject illegal timelines / empty index.
4. **Export/cut readiness (tiered)**: errors block; warnings allow continue with explicit `force`.
5. **Extension seams**: later insert-segment, per-segment regenerate, player time-pick, multi-format export do not require re-modeling.

### Non-goals

- Player “set start/end from playhead” buttons (documented follow-up).
- Insert new segment from video list / AI regenerate one segment.
- Real JianYing draft version chasing; new export formats (EDL/FCPXML).
- Domain-modeling texts/voiceover.
- Full OO rewrite of `plan_daily_vlog` AI path (generation may still produce dict, then `Plan.from_dict`).

### Success criteria

- User can reorder/delete/edit title & timeline in UI; refresh after save keeps changes.
- Bad `use_timeline` cannot be saved silently.
- Export/cut surfaces errors/warnings; errors cannot be force-skipped.
- CLI `export` / `cut` and UI share the same readiness rules.
- Legacy `*_plan.json` without `_schema_version` still loads; save writes current artifact schema version.

## 2. Current state (baseline)

| Surface | Behavior today |
| --- | --- |
| `editor-plan.js` | Meta fields + sequence list; editable `reason` / `voiceover_hint` only; click → preview; cut + jianying export buttons |
| `PUT /api/plan` | Atomic write of raw JSON body — no validation |
| Plan JSON shape (prompt) | `day_title`, `theme`, `total_estimated_sec`, `sequence[]` (`index`, `title`, `reason`, `use_timeline`, `voiceover_hint`), `opening_tip`, `ending_tip`, `_confidence` |
| `parse_time_range` | `clio/cut.py` — single parser for `HH:MM:SS` / `MM:SS` ranges; requires end > start |
| Artifact versioning | `clio/schema.py`: `_schema_version`, `add_schema_version`, `check_schema_version` |
| Export | `clio/export/jianying.py` consumes plan dict; skips missing video materials with a log line |
| Cut | `run_cut_all` reads plan file; no preflight checklist |

## 3. Architecture

### Principle

Introduce a **Plan domain layer** as the only boundary for “valid plan” on write and readiness paths. AI generation, disk JSON, and jianying may still use dicts at the edges, but **persist / validate / readiness** must go through the domain layer.

### Modules

```text
clio/plan_model.py          # Plan, PlanSegment, from_dict/to_dict, mutate helpers, validate_for_save
clio/plan_readiness.py      # check_plan_export_readiness → errors/warnings
clio/ui/routes/plan.py      # PUT validates; POST /api/plan/readiness
clio/ui/routes/export.py    # readiness before export
clio/tasks/cut.py           # readiness before cut (or shared helper at call site)
clio/export/jianying.py     # still accepts dict (plan.to_dict()); no forced internal rewrite
clio/ui/static/src/
  plan-edit.js              # pure reorder / remove / patch (vitest)
  editor-plan.js            # DOM: drag, delete, fields, checklist panel
```

### Data flow

```text
Disk dayN_plan.json
  → Plan.from_dict (legacy OK; missing _schema_version treated as v1 via check_schema_version)
  → UI holds plain object (to_dict); local edits + dirty
  → PUT body
  → Plan.from_dict + validate_for_save
  → to_dict + add_schema_version → _save_atomic

Export / cut
  → load plan → Plan.from_dict
  → check_plan_export_readiness(plan, video_index, offline_set, source=...)
  → errors? → reject (UI may force only warnings)
  → existing export_plan / run_cut_all(dict)
```

### Domain sketch

```python
@dataclass
class PlanSegment:
    index: str
    title: str = ""
    reason: str = ""
    use_timeline: str = ""
    voiceover_hint: str = ""
    extras: dict = field(default_factory=dict)  # preserve unknown segment keys

@dataclass
class Plan:
    day_title: str = ""
    theme: str = ""
    total_estimated_sec: int | float = 180
    opening_tip: str = ""
    ending_tip: str = ""
    sequence: list[PlanSegment] = field(default_factory=list)
    confidence: float | None = None  # maps _confidence
    extras: dict = field(default_factory=dict)  # preserve unknown top-level keys

    def reorder(self, from_i: int, to_i: int) -> None: ...
    def remove_at(self, i: int) -> PlanSegment: ...
    def validate_for_save(self) -> list[Issue]: ...  # hard errors only
```

Round-trip rules:

- Unknown fields never dropped (`extras` on plan and segment).
- `_confidence` ↔ `confidence` in from/to dict.
- Reuse global `_schema_version` via `clio.schema` — do not invent a second version field name.
- Timeline parsing always via `clio.cut.parse_time_range`.

### API surface (incremental REST)

| Method | Path | Role |
| --- | --- | --- |
| GET | `/api/plan?day=` | Unchanged JSON body (optional future normalize) |
| PUT | `/api/plan?day=` | `from_dict` → `validate_for_save` → write; 400 + `issues` on failure |
| POST | `/api/plan/readiness` | Body `{ day, source?, plan? }` → `{ ok, errors[], warnings[] }` |
| POST | `/api/export` | Run readiness on **disk** plan; `force: true` ignores **warnings only** |
| POST | `/api/cut` | Same as export |

**Readiness vs dirty buffer:** `POST /api/plan/readiness` may include an optional `plan` object (current editor buffer). When present, validate that object (no disk write). When absent, load `day` from disk. Export/cut always use the **saved** file — UI must prompt save if dirty before those actions (see §5). This avoids stale checks after local reorder/delete without inventing PATCH.

UI structural edits are **local** (`state.plan` + dirty + full PUT on save). Command-style `PATCH /segments` is deferred (insert/regenerate era).

### Issue shape

```text
Issue = {
  level: "error" | "warning",
  code: str,           # stable machine code, e.g. "timeline_invalid"
  message: str,        # Chinese user-facing
  segment_index?: int  # 0-based in sequence when applicable
}
```

## 4. Validation and readiness rules

### `validate_for_save` (hard → HTTP 400)

| Rule | Behavior |
| --- | --- |
| `sequence` must be a list | else error |
| Each segment needs non-empty `index` (stringified) | empty → error |
| Non-empty `use_timeline` | must parse via `parse_time_range`, end > start |
| Empty `sequence` | **allowed on save** (user may clear while reordering) |
| Unknown keys | kept in extras |

### `check_plan_export_readiness`

| Level | Examples |
| --- | --- |
| **error** | Missing plan file; empty sequence; illegal/unparseable `use_timeline` when non-empty; `index` not found in project video set at all |
| **warning** | Video offline; empty `use_timeline`; empty `title`/`reason`; total estimated duration very short/long; original source missing file but compressed exists |

`force=true`: skip warnings only; errors still 400.

CLI: same defaults; `--force` ignores warnings only (wire when implementing cut/export CLI paths if flags already exist, else add consistently).

### Error presentation (UI)

- PUT failure: toast + per-segment highlight when `segment_index` set.
- Readiness panel below sequence, above cut/export: red errors / yellow warnings; click scrolls to row.
- Export/cut without prior panel check: backend still enforces same `issues` payload shape.

### Concurrency / IO

- Persist via existing `_save_atomic`.
- No plan lock; last write wins (same as texts).
- If video/offline resolution fails: warning `media_status_unknown`, not a false error.

## 5. UI design

### Plan panel changes (`editor-plan.js` + `plan-edit.js`)

1. **Meta**: existing theme / opening / ending; also edit `day_title` when present.
2. **Sequence list**
   - Drag handle reorder; **↑ / ↓** buttons for a11y fallback.
   - Editable: `title`, `use_timeline` (text), `reason`, `voiceover_hint`.
   - Delete + confirm.
   - Click non-input area: keep preview jump behavior.
3. **Readiness panel**
   - On open plan / after dirty: debounce ~400ms → `POST /api/plan/readiness` with `{ day, source, plan: state.plan }` so unsaved edits are checked.
   - Errors disable primary export/cut actions.
   - Warnings only: confirm dialog, then request with `force: true` (after save if dirty).
4. **Dirty before export/cut**: prompt to save first (no silent auto-save); then readiness/export use disk.

### Frontend pure helpers (`plan-edit.js`)

- `reorderSequence(sequence, from, to) → newSequence`
- `removeSegment(sequence, index) → newSequence`
- `patchSegment(segment, fields) → newSegment`

No DOM in this module; vitest covers boundaries (first/last reorder, remove mid-list).

## 6. AI write-path normalization

When `tasks/plan.py` (or equivalent) writes a new plan after `plan_daily_vlog`:

1. `Plan.from_dict(result)`
2. `to_dict()` + `add_schema_version`
3. Atomic write

Keeps new files clean without rewriting the LLM prompt contract.

## 7. Phased delivery

| Phase | Scope | Done when |
| --- | --- | --- |
| **P1 Domain** | `plan_model.py` + pytest (legacy roundtrip, validate, reorder, remove) | Unit green without UI |
| **P2 Write path** | PUT validate; AI plan write normalize | Bad timeline rejected on save |
| **P3 Readiness** | `plan_readiness.py` + POST readiness; export/cut gated | API/CLI block errors |
| **P4 UI edit** | `plan-edit.js` + drag/delete/fields + dirty/save | Structural edit usable |
| **P5 UI checklist** | Panel + button gating + force confirm | Day-flow closed loop |

Commit style: one feature/fix per commit; Chinese UI copy, English commits (project convention).

## 8. Testing matrix

**pytest**

- Legacy JSON without `_schema_version` / missing optional fields.
- Invalid timeline, empty index, empty sequence: save vs readiness split.
- Offline / missing index error–warning tiers.
- PUT 400 body shape; export/cut reject errors; `force` warnings only.
- Roundtrip preserves extras and `_confidence`.

**vitest**

- Reorder edges; remove; patch does not mutate input unexpectedly.

## 9. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| UI plain object drifts from backend model | Full PUT body; `from_dict` is source of truth; pure plan-edit helpers |
| jianying skips missing video vs readiness error | Align: **completely unresolved index = error**; jianying skip remains defensive only |
| `editor-plan.js` grows further | New logic in `plan-edit.js`; DOM stays in editor-plan |
| Global artifact version vs plan evolution | Field compatibility via `extras`; breaking changes bump global artifact version when needed |

## 10. Follow-ups

| Item | Status |
| --- | --- |
| Player playhead → `use_timeline` start/end buttons | **Done** (same day follow-up). **Timebase (2026-07-19):** write path uses `planSecFromPlayer(player.currentTime, offset_sec)` so values match preview seek (`plan + offset`); require open clip = segment video |
| Insert segment (prompt index / end insert) | **Done** (same day follow-up) |
| Accordion card density (R-030) | **Done** (2026-07-19) — collapsed list + expand-to-edit; see `2026-07-19-plan-seg-card-density-design.md` |
| Composite / cut-output plan preview (R-031) | Open — still source-video hopping |
| Per-segment AI regenerate | **Declined** (2026-07-17) — use structural edit + full `plan` re-run |
| Incremental PATCH segment APIs | Out of scope (local edit + full PUT is enough) |
| EDL / FCPXML / other NLE intermediates | Out of scope |
| JianYing real draft version compatibility | Deferred product-wide |

## 11. Decisions log

| Decision | Choice | Rationale |
| --- | --- | --- |
| Product route | A — plan edit + readiness | Last mile plan → cut/export |
| Architecture | Domain model (approach 3), incremental | Extensibility without big-bang rewrite |
| Edit depth | Standard + insert + playhead bounds | Regen declined |
| Timeline UX | Text + playhead start/end buttons | Follow-up shipped same day |
| Readiness UX | Tiered: error block / warning force | Blocks real failures without nags |
| Empty sequence on save | Allowed | Users may clear while rebuilding order |
| Mutation API | Local edit + full PUT | Avoid PATCH surface until insert/regen |
| Dirty readiness | Optional `plan` in readiness body | Check buffer without write; export still disk-only |
| Schema field | Reuse `_schema_version` | Match existing artifacts |
