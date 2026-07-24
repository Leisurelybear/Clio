# Plan Source Inputs — Design

Date: 2026-07-24  
Status: draft for review  
Scope: Record which analysis videos fed each generated plan (`source_inputs` on `*_plan.json`).

## Goal

Every successfully generated day plan JSON must record the **input pool** of videos that were fed to the planner (after `files=` / day filters), so operators can audit selection-scoped plans and answer “which clips was this plan based on?” without re-deriving from `texts/` + run flags.

## Non-goals

- UI display of the input pool (optional later)
- Export / cut / readiness validation against `source_inputs`
- Backfill of old plans missing the field
- Side-car files (e.g. `day1_plan.sources.json`)
- Recording only sequence members (that is already implied by `sequence[].index`)
- Extra fields: paths, titles, `match_stem`, compressed filename (YAGNI)
- Changing the AI prompt or model output schema
- Schema major-version bump

## Background

| Fact | Detail |
| --- | --- |
| Write path | `run_plan_vlog` builds `clips[]` from `texts/*.json`, optional `files=` + `filter_by_day`, then `plan_daily_vlog` → `Plan.from_dict` → atomic JSON + md |
| Identity | Clips already carry `index`, `source_stem`, `match_stem` from `load_identity` / fallbacks |
| Selection | R-033 I1: `files is not None` bypasses skip-existing; result still overwrites `{day}_plan.json` — `source_inputs` makes that subset auditable |
| Model | `Plan` keeps unknown top-level keys in `extras` and round-trips them via `to_dict()` |
| Existing meta | `_transcripts_missing`, `_schema_version` already written post-AI on the same dict |

User choices (brainstorm 2026-07-24):

1. **Purpose:** input-pool provenance (not “only sequence members”).
2. **Granularity:** `index` + `source_stem` per entry.
3. **Surfaces:** JSON required; plan.md section on successful generation; no UI this round.
4. **Shape:** top-level `source_inputs` array on plan JSON (Approach A).

## Data model

### Field

Top-level key on `{day_label}_plan.json`:

```json
"source_inputs": [
  {"index": "001", "source_stem": "GL010684"},
  {"index": "002", "source_stem": "DJI_0042"}
]
```

| Key | Type | Meaning |
| --- | --- | --- |
| `index` | string | Zero-padded index as fed to the planner (`format_index`, same as clip `index`) |
| `source_stem` | string | Original stem: `identity.original_stem` if present, else `Path(source_file).stem` or artifact stem fallback already used when building clips |

### Ordering

Same order as the `clips` list passed to `plan_daily_vlog` (sorted texts scan after filters). Stable and human-readable.

### Semantics

| Situation | `source_inputs` |
| --- | --- |
| Full plan (`files is None`) | All clips that passed day/label filters |
| Selection plan (`files=[...]`) | Only clips matching selection |
| Empty clips | No plan write (existing early return); field N/A |
| Skip-existing short-circuit | Unchanged file returned as-is (may lack field if legacy) |
| AI returns a spurious `source_inputs` | **Overwrite** with server-built list after `Plan.to_dict()` (authoritative) |
| UI PUT plan body | Preserve client-supplied value if present; do not recompute from texts |
| Legacy plan missing key | Consumers treat as unknown; no error |

### Compatibility

- Additive only; do not require `_schema_version` bump for readers that ignore unknown keys.
- `Plan.from_dict` / `to_dict`: keep `source_inputs` in `extras` (do **not** add to `_PLAN_KNOWN` unless we later want first-class accessors — default: extras is enough).
- If later first-class field is desired, that is a separate change; this design deliberately avoids expanding `_PLAN_KNOWN` so editor round-trips stay simple.

## Write path

Sole writer of authoritative values: `clio/tasks/plan.py` → `run_plan_vlog`.

```text
clips = [...]                    # after files= / day filters
if not clips: return None

plan = plan_daily_vlog(clips, ...)
plan = Plan.from_dict(plan).to_dict()
plan["source_inputs"] = [
    {"index": c["index"], "source_stem": c["source_stem"]}
    for c in clips
]
# existing: _transcripts_missing, add_schema_version
write_json_atomic(out_json, plan)
# md: optional section (below)
```

### plan.md (required on successful generation)

Written in the same `run_plan_vlog` success path as JSON (not a separate optional job).  
After theme / duration block, before “## 推荐剪辑顺序”:

```markdown
## 规划素材

- `001` GL010684
- `002` DJI_0042
```

Empty `source_inputs` should not happen on successful write; if empty list, omit the section.

### What not to change

- `run_plan_all_days` / `trip_plan.json`: no per-day video list on the trip summary (day plans already hold it).
- `handle_put_plan`: no forced recompute.
- Preview / export / cut: out of scope.

## Error handling

- Building `source_inputs` is pure dict projection; no I/O.
- Missing `source_stem` on a clip: write `""` (should be rare given current clip builder).
- MD write failures: existing atomic write raises as today; no special case.
- Cancel before AI returns: no plan file update (unchanged).

## Testing

Add/extend under `clio/tests/test_tasks_plan.py` (and plan_model if needed):

| Case | Expect |
| --- | --- |
| Full plan generation | `source_inputs` length == clips; entries match index/stem |
| `files=["A"]` | Only A’s entry in `source_inputs` |
| Shape | Each item has only `index` and `source_stem` (string) |
| AI mock injects `source_inputs` | Disk value is still server list from clips |
| `Plan.from_dict` → `to_dict` with field present | Field preserved (extras) |
| Skip-existing with pre-written plan lacking field | Return as-is; no crash |

No UI / e2e required this round.

## Success criteria

1. Every newly generated `{day}_plan.json` includes `source_inputs` aligned with that run’s filtered clips.
2. Selection-scoped plans list only selected stems.
3. Plans and tools that ignore the field continue to work (legacy + editor PUT).
4. On successful generation, plan.md includes a short 规划素材 section matching `source_inputs`.
5. Unit tests above are green.

## Implementation sketch (for planning skill)

1. Helper `_source_inputs_from_clips(clips) -> list[dict]` in `plan.py` (or private inline).
2. Assign after `Plan.to_dict()`, before schema version / transcripts flag order: either order is fine as long as both land on disk; prefer **source_inputs then transcripts flag then schema** for readability.
3. MD section builder.
4. Tests (TDD: fail on missing field first).
5. No ROADMAP product ID unless user assigns one; optional one-line ROADMAP note under plan/editor residuals.

## Open questions (resolved)

| Q | Decision |
| --- | --- |
| Input pool vs sequence-only? | Input pool |
| Field richness? | index + source_stem |
| JSON / md / UI? | JSON + md section on success; no UI |
| Placement? | Top-level `source_inputs` |
| First-class on `Plan`? | No — extras passthrough |
| Backfill? | No |
