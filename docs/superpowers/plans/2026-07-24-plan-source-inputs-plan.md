# Plan Source Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every successfully generated day plan JSON records the input-pool videos fed to the planner as `source_inputs: [{index, source_stem}]`, with a matching plan.md section.

**Architecture:** After `Plan.from_dict(...).to_dict()` in `run_plan_vlog`, overwrite `plan["source_inputs"]` from the already-filtered `clips` list (authoritative server list; AI output discarded). Keep the field in `Plan.extras` (do not add to `_PLAN_KNOWN`). Extend plan.md with a short 规划素材 list. Unit tests in `test_tasks_plan.py` + one extras round-trip in `test_plan_model.py`.

**Tech Stack:** Python 3.10+, pytest, existing `clio.tasks.plan` / `clio.plan_model` / atomic write helpers.

**Spec:** `docs/superpowers/specs/2026-07-24-plan-source-inputs-design.md`

## Global Constraints

- Input pool only (not sequence-only); fields: `index` (str) + `source_stem` (str)
- Top-level key name exactly `source_inputs`
- Overwrite any AI-supplied `source_inputs` after `Plan.to_dict()`
- Do not add `source_inputs` to `_PLAN_KNOWN` (extras passthrough)
- No UI / export / readiness / backfill / schema major bump
- TDD: failing test before production code; Chinese dialogue, English commits
- One feature commit per logical unit; no push unless user asks

## File map

| File | Role |
| --- | --- |
| `clio/tasks/plan.py` | Helper + write `source_inputs` + md section |
| `clio/tests/test_tasks_plan.py` | Generation / selection / overwrite / md / skip tests |
| `clio/tests/test_plan_model.py` | extras round-trip for `source_inputs` |
| `clio/plan_model.py` | No change (extras already works) |

---

### Task 1: Helper + JSON `source_inputs` on plan generation

**Files:**
- Modify: `clio/tasks/plan.py` (helper near top; assign after `Plan.to_dict()`)
- Modify: `clio/tests/test_tasks_plan.py`
- Test: `clio/tests/test_tasks_plan.py`

**Interfaces:**
- Produces: `_source_inputs_from_clips(clips: list[dict]) -> list[dict[str, str]]`
- Consumes: each clip dict has `index` and `source_stem` keys (already built in `run_plan_vlog`)

- [ ] **Step 1: Write the failing tests**

Append to `clio/tests/test_tasks_plan.py` (reuse existing `cfg`, `_write_text` fixtures):

```python
def _fake_plan_payload(clips, **kwargs):
    return {
        "day_title": "Selected",
        "theme": "subset",
        "total_estimated_sec": 60,
        "opening_tip": "",
        "ending_tip": "",
        "sequence": [
            {"index": c["index"], "title": c["title"], "use_timeline": "00:00-00:10"} for c in clips
        ],
    }


class TestPlanSourceInputs:
    def test_full_plan_writes_source_inputs(self, cfg: AppConfig):
        from clio.tasks.plan import run_plan_vlog

        _write_text(cfg, "001_A.json", "A", 1)
        _write_text(cfg, "002_B.json", "B", 2)

        with patch("clio.tasks.plan.plan_daily_vlog", side_effect=_fake_plan_payload):
            result = run_plan_vlog(cfg, day_label="day1", files=None, overwrite=True)

        assert result is not None
        si = result["source_inputs"]
        assert si == [
            {"index": "001", "source_stem": "A"},
            {"index": "002", "source_stem": "B"},
        ]
        on_disk = json.loads((cfg.plans_dir / "day1_plan.json").read_text(encoding="utf-8"))
        assert on_disk["source_inputs"] == si

    def test_files_selection_subset_in_source_inputs(self, cfg: AppConfig):
        from clio.tasks.plan import run_plan_vlog

        _write_text(cfg, "001_A.json", "A", 1)
        _write_text(cfg, "002_B.json", "B", 2)

        with patch("clio.tasks.plan.plan_daily_vlog", side_effect=_fake_plan_payload):
            result = run_plan_vlog(cfg, day_label="day1", files=["A"], overwrite=True)

        assert result is not None
        assert result["source_inputs"] == [{"index": "001", "source_stem": "A"}]

    def test_ai_supplied_source_inputs_are_overwritten(self, cfg: AppConfig):
        from clio.tasks.plan import run_plan_vlog

        _write_text(cfg, "001_A.json", "A", 1)

        def _poisoned(clips, config, day_label="day1", **kwargs):
            payload = _fake_plan_payload(clips)
            payload["source_inputs"] = [{"index": "999", "source_stem": "FAKE"}]
            return payload

        with patch("clio.tasks.plan.plan_daily_vlog", side_effect=_poisoned):
            result = run_plan_vlog(cfg, day_label="day1", overwrite=True)

        assert result["source_inputs"] == [{"index": "001", "source_stem": "A"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest clio/tests/test_tasks_plan.py::TestPlanSourceInputs -q
```

Expected: FAIL — `KeyError: 'source_inputs'` or assert on missing key.

- [ ] **Step 3: Minimal implementation**

In `clio/tasks/plan.py`, after `_analysis_day_label` / near other private helpers, add:

```python
def _source_inputs_from_clips(clips: list[dict]) -> list[dict[str, str]]:
    """Build authoritative input-pool provenance for a generated plan."""
    return [
        {
            "index": str(c.get("index") or ""),
            "source_stem": str(c.get("source_stem") or ""),
        }
        for c in clips
    ]
```

In `run_plan_vlog`, after `plan = plan_obj.to_dict()` and **before** `_transcripts_missing` / `add_schema_version`:

```python
    plan_obj = Plan.from_dict(plan)
    plan = plan_obj.to_dict()
    plan["source_inputs"] = _source_inputs_from_clips(clips)
    if config.plan.use_transcripts:
        plan["_transcripts_missing"] = not transcripts_map
    plan = add_schema_version(plan)
    write_json_atomic(out_json, plan)
```

Do not touch skip-existing early return.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest clio/tests/test_tasks_plan.py -q
```

Expected: all pass (including existing I1 tests).

- [ ] **Step 5: Commit**

```bash
git add clio/tasks/plan.py clio/tests/test_tasks_plan.py
git commit -m "$(cat <<'EOF'
feat(plan): write source_inputs input-pool on generated plans

Record index + source_stem for every clip fed to the planner so
selection-scoped plans are auditable.
EOF
)"
```

---

### Task 2: plan.md 规划素材 section

**Files:**
- Modify: `clio/tasks/plan.py` (md `lines` builder after theme block)
- Modify: `clio/tests/test_tasks_plan.py`
- Test: `clio/tests/test_tasks_plan.py`

**Interfaces:**
- Consumes: `plan["source_inputs"]` from Task 1
- Produces: md section `## 规划素材` with lines `- \`{index}\` {source_stem}`

- [ ] **Step 1: Write the failing test**

```python
    def test_plan_md_lists_source_inputs(self, cfg: AppConfig):
        from clio.tasks.plan import run_plan_vlog

        _write_text(cfg, "001_A.json", "A", 1)
        _write_text(cfg, "002_B.json", "B", 2)

        with patch("clio.tasks.plan.plan_daily_vlog", side_effect=_fake_plan_payload):
            run_plan_vlog(cfg, day_label="day1", overwrite=True)

        md = (cfg.plans_dir / "day1_plan.md").read_text(encoding="utf-8")
        assert "## 规划素材" in md
        assert "`001` A" in md
        assert "`002` B" in md
        # section before sequence
        assert md.index("## 规划素材") < md.index("## 推荐剪辑顺序")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest clio/tests/test_tasks_plan.py::TestPlanSourceInputs::test_plan_md_lists_source_inputs -q
```

Expected: FAIL — `## 规划素材` not in md.

- [ ] **Step 3: Minimal implementation**

In `run_plan_vlog` md builder, change the initial `lines` construction to insert the section after duration and before sequence:

```python
    lines = [
        f"# {plan.get('day_title', day_label)}",
        "",
        f"**主题**: {plan.get('theme', '')}",
        f"**预估总时长**: {plan.get('total_estimated_sec', '')} 秒",
        "",
    ]
    source_inputs = plan.get("source_inputs") or []
    if source_inputs:
        lines.append("## 规划素材")
        lines.append("")
        for entry in source_inputs:
            idx = entry.get("index", "?")
            stem = entry.get("source_stem", "")
            lines.append(f"- `{idx}` {stem}")
        lines.append("")
    lines.append("## 推荐剪辑顺序")
```

Keep the existing `for item in plan.get("sequence", []):` loop and opening/ending tips unchanged after that.

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest clio/tests/test_tasks_plan.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clio/tasks/plan.py clio/tests/test_tasks_plan.py
git commit -m "$(cat <<'EOF'
feat(plan): list source_inputs in plan.md 规划素材 section
EOF
)"
```

---

### Task 3: Extras round-trip + skip-existing regression

**Files:**
- Modify: `clio/tests/test_plan_model.py`
- Modify: `clio/tests/test_tasks_plan.py`
- Test: same

**Interfaces:**
- Consumes: `Plan.from_dict` / `to_dict` extras behavior (no production change expected)

- [ ] **Step 1: Write the failing tests**

In `clio/tests/test_plan_model.py`:

```python
def test_source_inputs_roundtrip_via_extras():
    raw = {
        "day_title": "d",
        "sequence": [{"index": "001", "use_timeline": "00:00-00:10"}],
        "source_inputs": [{"index": "001", "source_stem": "A"}],
    }
    out = Plan.from_dict(raw).to_dict()
    assert out["source_inputs"] == [{"index": "001", "source_stem": "A"}]
```

In `TestPlanSourceInputs` (`test_tasks_plan.py`):

```python
    def test_skip_existing_preserves_plan_without_source_inputs(self, cfg: AppConfig):
        """Legacy plan without the field is returned as-is on skip."""
        from clio.tasks.plan import run_plan_vlog

        _write_text(cfg, "001_A.json", "A", 1)
        legacy = {
            "day_title": "Legacy",
            "theme": "old",
            "total_estimated_sec": 10,
            "sequence": [{"index": "001", "title": "A", "use_timeline": "00:00-00:05"}],
        }
        (cfg.plans_dir / "day1_plan.json").write_text(json.dumps(legacy), encoding="utf-8")
        (cfg.plans_dir / "day1_plan.md").write_text("# legacy", encoding="utf-8")

        with patch("clio.tasks.plan.plan_daily_vlog") as mock_plan:
            result = run_plan_vlog(cfg, day_label="day1", files=None, overwrite=False)

        mock_plan.assert_not_called()
        assert result is not None
        assert "source_inputs" not in result
```

- [ ] **Step 2: Run tests**

Run:

```bash
python -m pytest clio/tests/test_plan_model.py::test_source_inputs_roundtrip_via_extras clio/tests/test_tasks_plan.py::TestPlanSourceInputs::test_skip_existing_preserves_plan_without_source_inputs -q
```

Expected: both PASS without production changes (documents extras + skip behavior). If round-trip fails, stop and fix `plan_model` only if extras is broken — should not be.

- [ ] **Step 3: Full related suite**

Run:

```bash
python -m pytest clio/tests/test_tasks_plan.py clio/tests/test_plan_model.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add clio/tests/test_plan_model.py clio/tests/test_tasks_plan.py
git commit -m "$(cat <<'EOF'
test(plan): cover source_inputs extras round-trip and skip legacy
EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| `source_inputs` top-level `{index, source_stem}` | Task 1 |
| Order = filtered clips order | Task 1 (clips scan order) |
| Full vs `files=` subset | Task 1 tests |
| Overwrite AI-supplied value | Task 1 test + assign after `to_dict` |
| Skip-existing unchanged / legacy missing field | Task 3 |
| plan.md 规划素材 section | Task 2 |
| extras passthrough / no `_PLAN_KNOWN` | Task 3 + non-change to plan_model |
| No UI / export / backfill / trip_plan | Out of scope (no tasks) |

## Placeholder / consistency self-check

- No TBD/TODO in steps
- Helper name `_source_inputs_from_clips` consistent across tasks
- Field name `source_inputs` consistent
- Commit messages English; one concern per commit
