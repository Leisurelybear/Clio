from __future__ import annotations

import pytest

from clio.plan_model import Plan


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
