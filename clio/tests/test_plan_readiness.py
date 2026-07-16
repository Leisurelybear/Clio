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
    assert r.ok
    assert r.warnings


def test_bad_timeline_error():
    r = check_plan_export_readiness(
        _plan([{"index": "001", "use_timeline": "nope", "title": "t", "reason": "r"}]),
        known_indices={"001"},
    )
    assert not r.ok
    assert any(i.code == "timeline_invalid" for i in r.errors)


def test_empty_known_indices_skips_index_missing():
    """When project index discovery finds nothing, do not mark every plan index missing."""
    r = check_plan_export_readiness(
        _plan([{"index": "001", "use_timeline": "00:00-00:05", "title": "t", "reason": "r"}]),
        known_indices=set(),
    )
    assert r.ok
    assert not any(i.code == "index_missing" for i in r.errors)


def test_none_known_indices_skips_index_missing():
    r = check_plan_export_readiness(
        _plan([{"index": "001", "use_timeline": "00:00-00:05", "title": "t", "reason": "r"}]),
        known_indices=None,
    )
    assert r.ok
    assert not any(i.code == "index_missing" for i in r.errors)
