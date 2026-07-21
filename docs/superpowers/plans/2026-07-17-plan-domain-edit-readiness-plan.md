# Plan Domain Edit & Export Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Plan domain model with structural UI editing (reorder / delete / timeline+title) and tiered export/cut readiness so bad plans cannot silently ship to JianYing or cut.

**Architecture:** Pure domain layer (`clio/plan_model.py`, `clio/plan_readiness.py`) owns validation and readiness. Routes and CLI call it; UI keeps a plain-object buffer, mutates via pure helpers in `plan-edit.js`, and saves with full `PUT /api/plan`. Optional `plan` body on readiness checks the dirty buffer without writing; export/cut always use disk.

**Tech Stack:** Python 3.11+ dataclasses, existing `parse_time_range` / `schema.add_schema_version` / `_save_atomic`, stdlib HTTP routes + Router registry, vanilla ES modules + Vitest, pytest.

## Global Constraints

- Chinese user-facing copy; English commits (`type(scope): subject`); one feature per commit.
- Reuse `_schema_version` via `clio.schema` — do not invent a second version field.
- Timeline parsing only through `clio.cut.parse_time_range`.
- `force` never ignores errors — warnings only.
- Empty `sequence` allowed on save; readiness marks it as error for export/cut.
- No player playhead pick, insert-segment, or PATCH segment APIs in this plan.
- Prefer pure functions + TDD; keep DOM out of `plan-edit.js`.

---

## File Structure

| File | Responsibility |
| --- | --- |
| Create `clio/plan_model.py` | `PlanIssue`, `PlanSegment`, `Plan`, from/to dict, reorder/remove, `validate_for_save` |
| Create `clio/plan_readiness.py` | `ReadinessResult`, `check_plan_export_readiness` |
| Create `clio/tests/test_plan_model.py` | Domain unit tests |
| Create `clio/tests/test_plan_readiness.py` | Readiness unit tests |
| Modify `clio/ui/routes/plan.py` | PUT validate; POST readiness; cut force + readiness gate |
| Modify `clio/ui/routes/export.py` | Export readiness gate + force |
| Modify `clio/ui/server.py` | Register `POST /api/plan/readiness`; import new handler |
| Modify `clio/tasks/plan.py` | Normalize AI plan through `Plan` before write (keep `add_schema_version`) |
| Modify `clio/tasks/cut.py` | Optional readiness gate helper or document call-site gate (route/CLI) |
| Modify `clio/main.py` | `export --force` / cut path readiness if cut CLI exists |
| Modify `clio/tests/test_routes_plan.py` | PUT 400; readiness handler |
| Modify `clio/tests/test_export_routes.py` | Export blocked / force |
| Create `clio/ui/static/src/plan-edit.js` | Pure reorder/remove/patch |
| Create `clio/ui/static/src/__tests__/plan-edit.test.js` | Vitest |
| Modify `clio/ui/static/src/editor-plan.js` | Structural edit UI + readiness panel + button gates |
| Modify `ROADMAP.md` | Track R-026 (or route-A item) open→done phases |

---

### Task 1: Plan domain model (`plan_model.py`)

**Files:**
- Create: `clio/plan_model.py`
- Test: `clio/tests/test_plan_model.py`

**Interfaces:**
- Produces:
  - `@dataclass PlanIssue(level: str, code: str, message: str, segment_index: int | None = None)` with `to_dict() -> dict`
  - `@dataclass PlanSegment(index: str, title: str = "", reason: str = "", use_timeline: str = "", voiceover_hint: str = "", extras: dict = ...)`
  - `@dataclass Plan(day_title: str = "", theme: str = "", total_estimated_sec: int | float = 180, opening_tip: str = "", ending_tip: str = "", sequence: list[PlanSegment] = ..., confidence: float | None = None, extras: dict = ...)`
  - `Plan.from_dict(data: dict) -> Plan`
  - `Plan.to_dict() -> dict` (maps `confidence` → `_confidence` when not None; does **not** call `add_schema_version` — callers do)
  - `Plan.reorder(from_i: int, to_i: int) -> None`
  - `Plan.remove_at(i: int) -> PlanSegment`
  - `Plan.validate_for_save() -> list[PlanIssue]` (errors only)

- [ ] **Step 1: Write failing tests**

Create `clio/tests/test_plan_model.py`:

```python
from __future__ import annotations

import pytest

from clio.plan_model import Plan, PlanSegment


def test_from_dict_legacy_roundtrip_preserves_extras_and_confidence():
    raw = {
        "day_title": "巴黎 day1",
        "theme": "漫步",
        "total_estimated_sec": 120,
        "opening_tip": "开",
        "ending_tip": "收",
        "sequence": [
            {
                "index": "001",
                "title": "塞纳河",
                "reason": "风景",
                "use_timeline": "00:10-00:40",
                "voiceover_hint": "旁白",
                "ai_extra": 1,
            }
        ],
        "_confidence": 0.8,
        "custom_top": "keep-me",
    }
    plan = Plan.from_dict(raw)
    out = plan.to_dict()
    assert out["day_title"] == "巴黎 day1"
    assert out["_confidence"] == 0.8
    assert out["custom_top"] == "keep-me"
    assert out["sequence"][0]["ai_extra"] == 1
    assert out["sequence"][0]["use_timeline"] == "00:10-00:40"


def test_validate_for_save_rejects_bad_timeline():
    plan = Plan.from_dict(
        {
            "day_title": "d",
            "sequence": [{"index": "001", "use_timeline": "00:50-00:10"}],
        }
    )
    issues = plan.validate_for_save()
    assert any(i.code == "timeline_invalid" and i.level == "error" for i in issues)
    assert issues[0].segment_index == 0


def test_validate_for_save_rejects_empty_index():
    plan = Plan.from_dict({"sequence": [{"index": "", "title": "x"}]})
    issues = plan.validate_for_save()
    assert any(i.code == "index_empty" for i in issues)


def test_validate_for_save_allows_empty_sequence():
    plan = Plan.from_dict({"day_title": "d", "sequence": []})
    assert plan.validate_for_save() == []


def test_validate_for_save_allows_empty_timeline():
    plan = Plan.from_dict({"sequence": [{"index": "001", "use_timeline": ""}]})
    assert plan.validate_for_save() == []


def test_reorder_and_remove():
    plan = Plan.from_dict(
        {
            "sequence": [
                {"index": "001", "title": "a"},
                {"index": "002", "title": "b"},
                {"index": "003", "title": "c"},
            ]
        }
    )
    plan.reorder(0, 2)
    assert [s.index for s in plan.sequence] == ["002", "003", "001"]
    removed = plan.remove_at(1)
    assert removed.index == "003"
    assert [s.index for s in plan.sequence] == ["002", "001"]


def test_from_dict_stringifies_index():
    plan = Plan.from_dict({"sequence": [{"index": 1}]})
    assert plan.sequence[0].index == "1"


def test_reorder_out_of_range_raises():
    plan = Plan.from_dict({"sequence": [{"index": "001"}]})
    with pytest.raises(IndexError):
        plan.reorder(0, 5)
```

- [ ] **Step 2: Run tests — expect fail**

Run: `python -m pytest clio/tests/test_plan_model.py -v`  
Expected: FAIL (`ModuleNotFoundError: clio.plan_model` or import error)

- [ ] **Step 3: Implement `clio/plan_model.py`**

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from clio.cut import parse_time_range

_SEGMENT_KNOWN = frozenset({"index", "title", "reason", "use_timeline", "voiceover_hint"})
_PLAN_KNOWN = frozenset(
    {
        "day_title",
        "theme",
        "total_estimated_sec",
        "opening_tip",
        "ending_tip",
        "sequence",
        "_confidence",
        "confidence",
        "_schema_version",  # strip on from_dict; re-added by callers
    }
)


@dataclass
class PlanIssue:
    level: str  # "error" | "warning"
    code: str
    message: str
    segment_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"level": self.level, "code": self.code, "message": self.message}
        if self.segment_index is not None:
            d["segment_index"] = self.segment_index
        return d


@dataclass
class PlanSegment:
    index: str
    title: str = ""
    reason: str = ""
    use_timeline: str = ""
    voiceover_hint: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanSegment:
        if not isinstance(data, dict):
            data = {}
        extras = {k: v for k, v in data.items() if k not in _SEGMENT_KNOWN}
        idx = data.get("index", "")
        if idx is None:
            idx = ""
        return cls(
            index=str(idx).strip() if not isinstance(idx, str) else idx.strip() if idx is not None else "",
            title=str(data.get("title") or ""),
            reason=str(data.get("reason") or ""),
            use_timeline=str(data.get("use_timeline") or "").strip(),
            voiceover_hint=str(data.get("voiceover_hint") or ""),
            extras=extras,
        )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "index": self.index,
            "title": self.title,
            "reason": self.reason,
            "use_timeline": self.use_timeline,
            "voiceover_hint": self.voiceover_hint,
        }
        d.update(self.extras)
        return d


@dataclass
class Plan:
    day_title: str = ""
    theme: str = ""
    total_estimated_sec: int | float = 180
    opening_tip: str = ""
    ending_tip: str = ""
    sequence: list[PlanSegment] = field(default_factory=list)
    confidence: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Plan:
        if not isinstance(data, dict):
            data = {}
        seq_raw = data.get("sequence", [])
        if not isinstance(seq_raw, list):
            seq_raw = []
        sequence = [PlanSegment.from_dict(s if isinstance(s, dict) else {}) for s in seq_raw]
        conf = data.get("_confidence", data.get("confidence"))
        try:
            confidence = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            confidence = None
        extras = {k: v for k, v in data.items() if k not in _PLAN_KNOWN}
        tes = data.get("total_estimated_sec", 180)
        try:
            total_estimated_sec = float(tes) if tes is not None else 180
        except (TypeError, ValueError):
            total_estimated_sec = 180
        return cls(
            day_title=str(data.get("day_title") or ""),
            theme=str(data.get("theme") or ""),
            total_estimated_sec=total_estimated_sec,
            opening_tip=str(data.get("opening_tip") or ""),
            ending_tip=str(data.get("ending_tip") or ""),
            sequence=sequence,
            confidence=confidence,
            extras=extras,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "day_title": self.day_title,
            "theme": self.theme,
            "total_estimated_sec": self.total_estimated_sec,
            "opening_tip": self.opening_tip,
            "ending_tip": self.ending_tip,
            "sequence": [s.to_dict() for s in self.sequence],
        }
        if self.confidence is not None:
            d["_confidence"] = self.confidence
        d.update(self.extras)
        return d

    def reorder(self, from_i: int, to_i: int) -> None:
        n = len(self.sequence)
        if not (0 <= from_i < n and 0 <= to_i < n):
            raise IndexError(f"reorder out of range: {from_i}->{to_i} (n={n})")
        item = self.sequence.pop(from_i)
        self.sequence.insert(to_i, item)

    def remove_at(self, i: int) -> PlanSegment:
        if not (0 <= i < len(self.sequence)):
            raise IndexError(f"remove_at out of range: {i}")
        return self.sequence.pop(i)

    def validate_for_save(self) -> list[PlanIssue]:
        issues: list[PlanIssue] = []
        for i, seg in enumerate(self.sequence):
            if not (seg.index or "").strip():
                issues.append(
                    PlanIssue(
                        level="error",
                        code="index_empty",
                        message=f"第 {i + 1} 段缺少视频 index",
                        segment_index=i,
                    )
                )
            tl = (seg.use_timeline or "").strip()
            if tl:
                try:
                    parse_time_range(tl)
                except ValueError as e:
                    issues.append(
                        PlanIssue(
                            level="error",
                            code="timeline_invalid",
                            message=f"第 {i + 1} 段时间轴无效: {e}",
                            segment_index=i,
                        )
                    )
        return issues
```

Fix `index` stringification in `PlanSegment.from_dict` to always `str(idx).strip()` when idx is not None/empty-aware:

```python
        raw_idx = data.get("index", "")
        if raw_idx is None:
            index = ""
        else:
            index = str(raw_idx).strip()
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python -m pytest clio/tests/test_plan_model.py -v`  
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add clio/plan_model.py clio/tests/test_plan_model.py
git commit -m "feat(plan): domain model Plan/PlanSegment with save validation"
```

---

### Task 2: PUT `/api/plan` validation + AI write normalize

**Files:**
- Modify: `clio/ui/routes/plan.py` (`handle_put_plan`)
- Modify: `clio/tasks/plan.py` (after `plan_daily_vlog`, before write)
- Modify: `clio/tests/test_routes_plan.py`
- Test: extend `clio/tests/test_plan_model.py` only if needed

**Interfaces:**
- Consumes: `Plan.from_dict`, `validate_for_save`, `to_dict`, `add_schema_version`
- Produces: PUT returns `{"ok": false, "error": str, "issues": [...]}` status 400 on validation failure

- [ ] **Step 1: Write failing route tests**

Append to `clio/tests/test_routes_plan.py`:

```python
class TestHandlePutPlanValidation:
    def test_rejects_invalid_timeline(self, tmp_path: Path):
        handler = MagicMock()
        handler._get_project_output.return_value = tmp_path / "output"
        handler._send_json = MagicMock()
        body = {
            "day_title": "d",
            "sequence": [{"index": "001", "use_timeline": "99:99-00:00"}],
        }
        handle_put_plan(handler, {"day": ["day1"]}, body)
        args = handler._send_json.call_args
        assert args[0][1] == 400
        assert args[0][0]["ok"] is False
        assert args[0][0]["issues"]

    def test_saves_normalized_plan_with_schema(self, tmp_path: Path):
        handler = MagicMock()
        proj_out = tmp_path / "output"
        handler._get_project_output.return_value = proj_out
        handler._send_json = MagicMock()
        body = {
            "day_title": "d",
            "sequence": [{"index": "001", "use_timeline": "00:00-00:10", "title": "t"}],
        }
        handle_put_plan(handler, {"day": ["day1"]}, body)
        handler._send_json.assert_called_once()
        assert handler._send_json.call_args[0][0]["ok"] is True
        saved = json.loads((proj_out / "plans" / "day1_plan.json").read_text(encoding="utf-8"))
        assert saved["sequence"][0]["index"] == "001"
        assert "_schema_version" in saved
```

Update existing `test_saves_plan` if it starts failing: body `{"title": "test plan"}` should still save (title in extras, empty sequence OK).

- [ ] **Step 2: Run tests — expect fail**

Run: `python -m pytest clio/tests/test_routes_plan.py::TestHandlePutPlanValidation -v`  
Expected: FAIL (no validation / no issues key)

- [ ] **Step 3: Implement PUT validation**

Replace `handle_put_plan` body logic in `clio/ui/routes/plan.py`:

```python
from clio.plan_model import Plan
from clio.schema import add_schema_version

def handle_put_plan(handler: HandlerProtocol, qs: dict[str, Any], obj: dict) -> None:
    day = qs.get("day", [""])[0]
    if not _is_safe_basename(day) or not day:
        return handler._send_json({"ok": False, "error": "forbidden"}, 403)
    proj_out = handler._get_project_output(qs)
    p = proj_out / "plans" / f"{day}_plan.json"
    plan = Plan.from_dict(obj if isinstance(obj, dict) else {})
    issues = plan.validate_for_save()
    if issues:
        return handler._send_json(
            {
                "ok": False,
                "error": issues[0].message,
                "issues": [i.to_dict() for i in issues],
            },
            400,
        )
    data = add_schema_version(plan.to_dict())
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    p.parent.mkdir(parents=True, exist_ok=True)
    _save_atomic(p, payload)
    handler._send_json({"ok": True, "path": str(p)})
```

- [ ] **Step 4: Normalize AI plan write in `tasks/plan.py`**

After `plan = plan_daily_vlog(...)` and optional `_transcripts_missing` assignment, replace direct `add_schema_version(plan)` write with:

```python
        from clio.plan_model import Plan

        plan_obj = Plan.from_dict(plan)
        # preserve pipeline-only keys that from_dict keeps via extras
        plan = add_schema_version(plan_obj.to_dict())
        write_json_atomic(out_json, plan)
```

Keep markdown generation reading `plan.get(...)` as today (dict after to_dict).

If `_transcripts_missing` must survive: set on dict **before** `from_dict` so it lands in `extras`, or set on `plan` after `to_dict`:

```python
        plan_obj = Plan.from_dict(plan)
        out = plan_obj.to_dict()
        if config.plan.use_transcripts:
            out["_transcripts_missing"] = not transcripts_map
        plan = add_schema_version(out)
        write_json_atomic(out_json, plan)
```

Remove the earlier `plan["_transcripts_missing"] = ...` line if moved here.

- [ ] **Step 5: Run tests**

Run:
```bash
python -m pytest clio/tests/test_routes_plan.py clio/tests/test_plan_model.py clio/tests/test_plan.py -q
```
Expected: PASS (fix any plan task tests if they assert exact write shape)

- [ ] **Step 6: Commit**

```bash
git add clio/ui/routes/plan.py clio/tasks/plan.py clio/tests/test_routes_plan.py
git commit -m "feat(plan): validate PUT body and normalize AI plan writes"
```

---

### Task 3: Readiness pure module

**Files:**
- Create: `clio/plan_readiness.py`
- Test: `clio/tests/test_plan_readiness.py`

**Interfaces:**
- Consumes: `Plan`, `PlanIssue`, `parse_time_range` (via plan or direct)
- Produces:
  - `@dataclass ReadinessResult(errors: list[PlanIssue], warnings: list[PlanIssue])` with `ok: bool` property (`not errors`), `to_dict()`
  - `check_plan_export_readiness(plan: Plan, *, known_indices: set[str] | None = None, offline_indices: set[str] | None = None, source: str = "compressed") -> ReadinessResult`

Rules (implement exactly):

| code | level | when |
| --- | --- | --- |
| `sequence_empty` | error | `not plan.sequence` |
| `timeline_invalid` | error | non-empty timeline fails `parse_time_range` |
| `index_empty` | error | empty index |
| `index_missing` | error | `known_indices is not None` and index not in set (normalize compare: strip; also try zero-pad? **compare as string equality after strip**; document that callers pass indices as in plan / videos) |
| `video_offline` | warning | index in `offline_indices` |
| `timeline_empty` | warning | empty use_timeline |
| `title_empty` | warning | empty title |
| `reason_empty` | warning | empty reason |
| `duration_short` | warning | `total_estimated_sec` < 30 |
| `duration_long` | warning | `total_estimated_sec` > 1800 |

If `known_indices is None`, skip `index_missing` (do not invent). If `offline_indices is None`, skip offline warnings.

- [ ] **Step 1: Write failing tests**

```python
from __future__ import annotations

from clio.plan_model import Plan
from clio.plan_readiness import check_plan_export_readiness


def _plan(seq, **kw):
    return Plan.from_dict({"day_title": "d", "sequence": seq, **kw})


def test_empty_sequence_error():
    r = check_plan_export_readiness(_plan([]), known_indices={"001"})
    assert not r.ok
    assert any(i.code == "sequence_empty" for i in r.errors)


def test_missing_index_error():
    r = check_plan_export_readiness(
        _plan([{"index": "099", "use_timeline": "00:00-00:05", "title": "t", "reason": "r"}]),
        known_indices={"001"},
    )
    assert any(i.code == "index_missing" for i in r.errors)


def test_offline_warning_only():
    r = check_plan_export_readiness(
        _plan([{"index": "001", "use_timeline": "00:00-00:05", "title": "t", "reason": "r"}]),
        known_indices={"001"},
        offline_indices={"001"},
    )
    assert r.ok
    assert any(i.code == "video_offline" for i in r.warnings)


def test_force_semantics_warnings_ok_errors_not():
    r = check_plan_export_readiness(
        _plan([{"index": "001", "use_timeline": "", "title": "", "reason": ""}]),
        known_indices={"001"},
    )
    # empty timeline/title/reason are warnings; still ok for force path
    assert r.ok
    assert r.warnings


def test_bad_timeline_error():
    r = check_plan_export_readiness(
        _plan([{"index": "001", "use_timeline": "nope", "title": "t", "reason": "r"}]),
        known_indices={"001"},
    )
    assert not r.ok
    assert any(i.code == "timeline_invalid" for i in r.errors)
```

- [ ] **Step 2: Run — expect fail**

Run: `python -m pytest clio/tests/test_plan_readiness.py -v`  
Expected: FAIL import

- [ ] **Step 3: Implement `clio/plan_readiness.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field

from clio.cut import parse_time_range
from clio.plan_model import Plan, PlanIssue


@dataclass
class ReadinessResult:
    errors: list[PlanIssue] = field(default_factory=list)
    warnings: list[PlanIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
        }


def check_plan_export_readiness(
    plan: Plan,
    *,
    known_indices: set[str] | None = None,
    offline_indices: set[str] | None = None,
    source: str = "compressed",
) -> ReadinessResult:
    del source  # reserved for original-vs-compressed nuance in callers
    result = ReadinessResult()
    if not plan.sequence:
        result.errors.append(
            PlanIssue(level="error", code="sequence_empty", message="规划 sequence 为空，无法导出/裁剪")
        )
        return result

    try:
        tes = float(plan.total_estimated_sec)
    except (TypeError, ValueError):
        tes = 180
    if tes < 30:
        result.warnings.append(
            PlanIssue(level="warning", code="duration_short", message=f"预估总时长过短（{tes} 秒）")
        )
    if tes > 1800:
        result.warnings.append(
            PlanIssue(level="warning", code="duration_long", message=f"预估总时长过长（{tes} 秒）")
        )

    known = {str(x).strip() for x in known_indices} if known_indices is not None else None
    offline = {str(x).strip() for x in offline_indices} if offline_indices is not None else set()

    for i, seg in enumerate(plan.sequence):
        idx = (seg.index or "").strip()
        if not idx:
            result.errors.append(
                PlanIssue(level="error", code="index_empty", message=f"第 {i + 1} 段缺少 index", segment_index=i)
            )
        elif known is not None and idx not in known:
            result.errors.append(
                PlanIssue(
                    level="error",
                    code="index_missing",
                    message=f"第 {i + 1} 段视频 [{idx}] 在项目中不存在",
                    segment_index=i,
                )
            )
        elif idx in offline:
            result.warnings.append(
                PlanIssue(
                    level="warning",
                    code="video_offline",
                    message=f"第 {i + 1} 段视频 [{idx}] 当前离线",
                    segment_index=i,
                )
            )

        tl = (seg.use_timeline or "").strip()
        if not tl:
            result.warnings.append(
                PlanIssue(
                    level="warning",
                    code="timeline_empty",
                    message=f"第 {i + 1} 段未填写 use_timeline",
                    segment_index=i,
                )
            )
        else:
            try:
                parse_time_range(tl)
            except ValueError as e:
                result.errors.append(
                    PlanIssue(
                        level="error",
                        code="timeline_invalid",
                        message=f"第 {i + 1} 段时间轴无效: {e}",
                        segment_index=i,
                    )
                )

        if not (seg.title or "").strip():
            result.warnings.append(
                PlanIssue(level="warning", code="title_empty", message=f"第 {i + 1} 段标题为空", segment_index=i)
            )
        if not (seg.reason or "").strip():
            result.warnings.append(
                PlanIssue(level="warning", code="reason_empty", message=f"第 {i + 1} 段理由为空", segment_index=i)
            )

    return result
```

- [ ] **Step 4: Run — expect pass**

Run: `python -m pytest clio/tests/test_plan_readiness.py -v`

- [ ] **Step 5: Commit**

```bash
git add clio/plan_readiness.py clio/tests/test_plan_readiness.py
git commit -m "feat(plan): export/cut readiness checker with error/warning tiers"
```

---

### Task 4: Readiness HTTP + export/cut gates + CLI `--force`

**Files:**
- Modify: `clio/ui/routes/plan.py` — add `handle_post_plan_readiness`; gate `handle_post_cut`
- Modify: `clio/ui/routes/export.py` — gate export
- Modify: `clio/ui/server.py` — import + `Route("POST", "/api/plan/readiness", "handle_post_plan_readiness")`
- Modify: `clio/main.py` — export (and cut if present) readiness + `--force`
- Modify: `clio/tests/test_routes_plan.py`, `clio/tests/test_export_routes.py`
- Modify: `clio/tests/test_server.py` only if route matrix lists every route explicitly

**Helper to build index sets** (put in `plan_readiness.py` or `plan.py` routes):

```python
def indices_from_video_entries(entries: list[dict]) -> tuple[set[str], set[str]]:
    """Return (known_indices, offline_indices) from /api/videos-like dicts.

    Expect keys: index (str), and offline signal via missing=True or offline=True
    or path that does not exist when path key present.
    """
```

For route handlers without full videos rebuild: scan `state` is UI-only. Backend should:

1. Load plan from disk or body.
2. Build known/offline from project videos — simplest reliable approach for v1:

```python
def collect_project_indices(cfg) -> tuple[set[str], set[str]]:
    known: set[str] = set()
    offline: set[str] = set()
    # From compressed dir stems "001_..." prefix
    from clio._constants import VIDEO_EXTS
    comp = cfg.compressed_dir
    if comp.is_dir():
        for p in comp.iterdir():
            if p.suffix.lower() in VIDEO_EXTS:
                stem = p.stem
                idx = stem.split("_", 1)[0]
                if idx.isdigit() or idx:
                    known.add(idx)
    # Also texts JSON index field
    texts = cfg.texts_dir
    if texts.is_dir():
        for jf in texts.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("index") is not None:
                known.add(str(data["index"]).strip())
    # Offline originals from videos.json if available
    try:
        from clio.tasks._video_loader import load_selected_videos
        # optional: if project tracks selection with missing paths, mark offline
    except Exception:
        pass
    return known, offline
```

Keep `collect_project_indices` practical: **known** = indices seen in compressed filenames prefix + texts `index`; **offline** = indices whose matched original path from identity/videos.json is missing when resolvable; if resolution fails, leave offline empty (avoid false errors). Unit-test the pure readiness module with explicit sets; route tests mock `collect_project_indices` or write temp compressed files.

- [ ] **Step 1: Failing tests for readiness handler**

```python
def test_readiness_with_inline_plan_empty_sequence(tmp_path):
    handler = MagicMock()
    handler._resolve_project_dir.return_value = tmp_path
    cfg = MagicMock()
    cfg.plans_dir = tmp_path / "plans"
    cfg.compressed_dir = tmp_path / "compressed"
    cfg.texts_dir = tmp_path / "texts"
    cfg.compressed_dir.mkdir()
    cfg.texts_dir.mkdir()
    handler._get_config.return_value = cfg
    handler._send_json = MagicMock()
    handle_post_plan_readiness(
        handler,
        {},
        {"day": "day1", "plan": {"day_title": "d", "sequence": []}},
    )
    payload = handler._send_json.call_args[0][0]
    assert payload["ok"] is False
    assert payload["errors"]
```

Export test: missing readiness error when sequence empty on disk; `force` still fails on errors; `force` succeeds when only warnings (mock checker or craft plan with offline only).

- [ ] **Step 2: Implement handlers**

`handle_post_plan_readiness`:

```python
def handle_post_plan_readiness(handler, qs, obj):
    day = (obj or {}).get("day") or qs.get("day", ["day1"])[0]
    if not _is_safe_basename(str(day)):
        return handler._send_json({"ok": False, "error": "forbidden"}, 403)
    source = (obj or {}).get("source") or "compressed"
    proj_dir = handler._resolve_project_dir(qs)
    cfg = handler._get_config(proj_dir)
    inline = (obj or {}).get("plan")
    if isinstance(inline, dict):
        plan = Plan.from_dict(inline)
    else:
        path = cfg.plans_dir / f"{day}_plan.json"
        if not path.is_file():
            return handler._send_json(
                {
                    "ok": False,
                    "errors": [{"level": "error", "code": "plan_missing", "message": f"规划文件不存在: {path}"}],
                    "warnings": [],
                },
                404,
            )
        plan = Plan.from_dict(json.loads(path.read_text(encoding="utf-8")))
    known, offline = collect_project_indices(cfg)
    result = check_plan_export_readiness(plan, known_indices=known, offline_indices=offline, source=source)
    handler._send_json(result.to_dict())
```

Export gate (top of `handle_post_export` after plan_path exists):

```python
    force = bool(obj.get("force"))
    plan = Plan.from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
    known, offline = collect_project_indices(cfg)
    result = check_plan_export_readiness(plan, known_indices=known, offline_indices=offline, source="original")
    if result.errors:
        handler._send_json({"ok": False, "error": result.errors[0].message, "issues": result.to_dict()}, 400)
        return
    if result.warnings and not force:
        handler._send_json(
            {
                "ok": False,
                "error": "规划存在警告，确认后请传 force: true",
                "issues": result.to_dict(),
                "needs_force": True,
            },
            400,
        )
        return
```

Same pattern for `handle_post_cut` with `source` from body.

CLI `export`: after loading plan, run readiness; if errors print and return 1; if warnings and not `args.force` print and return 1; add `p_export.add_argument("--force", action="store_true", ...)`.

- [ ] **Step 3: Register route in `server.py`**

```python
from clio.ui.routes.plan import (
    handle_get_plan,
    handle_get_plans,
    handle_post_cut,
    handle_post_plan_readiness,
    handle_put_plan,
)
# ...
Route("POST", "/api/plan/readiness", "handle_post_plan_readiness"),
```

Ensure string resolver / handler map includes the new name (same pattern as other handlers in `make_handler`).

- [ ] **Step 4: Run tests**

```bash
python -m pytest clio/tests/test_routes_plan.py clio/tests/test_export_routes.py clio/tests/test_plan_readiness.py clio/tests/test_server.py -q
```

- [ ] **Step 5: Commit**

```bash
git add clio/ui/routes/plan.py clio/ui/routes/export.py clio/ui/server.py clio/main.py clio/plan_readiness.py clio/tests/
git commit -m "feat(plan): readiness API and export/cut force gates"
```

---

### Task 5: Frontend pure `plan-edit.js`

**Files:**
- Create: `clio/ui/static/src/plan-edit.js`
- Create: `clio/ui/static/src/__tests__/plan-edit.test.js`

**Interfaces:**
- Produces:
  - `reorderSequence(sequence, fromIndex, toIndex) -> newSequence` (immutable)
  - `removeSegment(sequence, index) -> newSequence`
  - `patchSegment(segment, fields) -> newSegment`

- [ ] **Step 1: Failing vitest**

```js
import { describe, it, expect } from 'vitest';
import { reorderSequence, removeSegment, patchSegment } from '../plan-edit.js';

describe('plan-edit', () => {
  const seq = [{ index: '001' }, { index: '002' }, { index: '003' }];

  it('reorders without mutating input', () => {
    const next = reorderSequence(seq, 0, 2);
    expect(next.map((s) => s.index)).toEqual(['002', '003', '001']);
    expect(seq[0].index).toBe('001');
  });

  it('removeSegment', () => {
    const next = removeSegment(seq, 1);
    expect(next.map((s) => s.index)).toEqual(['001', '003']);
    expect(seq).toHaveLength(3);
  });

  it('patchSegment merges fields', () => {
    const s = { index: '001', title: 'a' };
    const next = patchSegment(s, { title: 'b', use_timeline: '00:00-00:01' });
    expect(next.title).toBe('b');
    expect(next.use_timeline).toBe('00:00-00:01');
    expect(s.title).toBe('a');
  });
});
```

- [ ] **Step 2: Implement**

```js
export function reorderSequence(sequence, fromIndex, toIndex) {
  const arr = sequence.slice();
  if (fromIndex < 0 || toIndex < 0 || fromIndex >= arr.length || toIndex >= arr.length) {
    return arr;
  }
  const [item] = arr.splice(fromIndex, 1);
  arr.splice(toIndex, 0, item);
  return arr;
}

export function removeSegment(sequence, index) {
  return sequence.filter((_, i) => i !== index);
}

export function patchSegment(segment, fields) {
  return { ...segment, ...fields };
}
```

- [ ] **Step 3: Run**

```bash
npm test -- --run clio/ui/static/src/__tests__/plan-edit.test.js
```

- [ ] **Step 4: Commit**

```bash
git add clio/ui/static/src/plan-edit.js clio/ui/static/src/__tests__/plan-edit.test.js
git commit -m "feat(ui): pure plan-edit helpers for reorder/remove/patch"
```

---

### Task 6: Plan panel structural edit UI

**Files:**
- Modify: `clio/ui/static/src/editor-plan.js`
- Optionally small CSS in `clio/ui/static/style.css` for drag handle / delete btn

**Behavior:**
1. Meta: add editable `day_title` alongside theme/opening/ending.
2. Each sequence row:
   - drag handle (`draggable=true` on handle or `li`)
   - ↑ / ↓ buttons calling `reorderSequence` + re-render or DOM move + `state.plan.sequence = ...; markDirty()`
   - inputs: `title`, `use_timeline`, `reason`, `voiceover_hint`
   - delete button → `confirm('删除此片段？')` → `removeSegment` → assign + `markDirty()` + re-`renderPlan()` (or incremental DOM)
3. On save failure with `issues`: `addToast` + optional `data-seg-error` class on rows.

Keep click-to-preview when target is not input/button.

Minimal drag implementation if full HTML5 DnD is noisy: **↑↓ only is acceptable for MVP** if drag is flaky — but prefer both. Spec requires drag handle + ↑↓; implement both.

Save path already uses full PUT; ensure invalid timeline surfaces new 400 `error` message (already in catch).

- [ ] **Step 1: Implement UI edits in `renderPlan` sequence loop** using `plan-edit.js` helpers.
- [ ] **Step 2: Manual smoke** (or extend vitest only for pure helpers already covered).
- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/src/editor-plan.js clio/ui/static/style.css
git commit -m "feat(ui): plan structural edit reorder delete title timeline"
```

---

### Task 7: Readiness panel + export/cut button gating

**Files:**
- Modify: `clio/ui/static/src/editor-plan.js`

**Behavior:**
1. After sequence list, mount `#plan-readiness` container.
2. `scheduleReadinessCheck` debounced 400ms:
   ```js
   api('POST', '/api/plan/readiness', {
     day: state.currentDay || 'day1',
     source: $('cut-source')?.value || 'compressed',
     plan: state.plan,
   })
   ```
3. Render errors (red) / warnings (yellow); click item → `document.querySelector(\`[data-preview-index="${segment_index}"]\`)?.scrollIntoView()`.
4. Export / cut click handlers:
   - if `state.dirty` → `confirm('有未保存修改，请先保存')` return (or offer save then continue — **prompt only**, no auto-save).
   - if last readiness has errors → toast + return.
   - if warnings only → `confirm('存在警告，仍要继续？')` then POST with `force: true`.
5. Wire `force: true` into existing export POST body and cut POST body.
6. Call `scheduleReadinessCheck` on open plan and after every structural/field change (`markDirty` sites).

- [ ] **Step 1: Implement panel + gates**
- [ ] **Step 2: Smoke checklist**
  - Empty sequence → export disabled / blocked
  - Bad timeline cannot save
  - Warning-only → confirm + force works
- [ ] **Step 3: Commit**

```bash
git add clio/ui/static/src/editor-plan.js
git commit -m "feat(ui): plan readiness panel and export/cut force confirm"
```

---

### Task 8: Docs / ROADMAP

**Files:**
- Modify: `ROADMAP.md` — add completed feature blurb under Remaining / Recently completed:

```markdown
| R-026 | Plan domain edit + export readiness (Route A) | Large | High |
```

Mark phases done as commits land; final:

```markdown
**Recently completed (2026-07-17 R-026):** Plan domain model, PUT validation,
readiness API, UI reorder/delete/timeline edit, export/cut force gates.
See `docs/superpowers/specs/2026-07-17-plan-domain-edit-readiness-design.md`.
```

- [ ] **Step 1: Update ROADMAP**
- [ ] **Step 2: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): mark R-026 plan domain edit readiness"
```

---

## Self-Review (plan vs spec)

| Spec requirement | Task |
| --- | --- |
| Plan/PlanSegment domain + extras | Task 1 |
| validate_for_save / empty sequence allowed | Task 1 |
| PUT validation + schema version | Task 2 |
| AI write normalize | Task 2 |
| Tiered readiness pure | Task 3 |
| POST readiness with optional plan body | Task 4 |
| export/cut force warnings only | Task 4 |
| CLI force | Task 4 |
| plan-edit pure helpers | Task 5 |
| UI reorder/delete/title/timeline | Task 6 |
| Readiness panel + dirty save prompt + force confirm | Task 7 |
| Follow-ups excluded | Not scheduled |
| ROADMAP | Task 8 |

No TBD placeholders. Types: `PlanIssue` / `ReadinessResult` / `check_plan_export_readiness` names consistent across tasks.

---

## Execution notes

- Prefer **subagent-driven-development**: one task per subagent, review before next.
- After Task 4, full pytest; after Task 5–7, vitest + targeted pytest.
- Do not push unless user asks.
