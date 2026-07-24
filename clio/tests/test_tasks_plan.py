"""Tests for clio/tasks/plan.py — run_plan_vlog selection + skip-existing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from clio.config import AppConfig
from clio.config.models import (
    AnalyzeConfig,
    GlobalConfig,
    GlobalPathsConfig,
    NamingConfig,
    PlanConfig,
    ProjectConfig,
    ProjectPathsConfig,
    ScriptConfig,
)


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    (tmp_path / "plans").mkdir()
    (tmp_path / "texts").mkdir()
    (tmp_path / "compressed").mkdir()
    (tmp_path / "videos").mkdir()
    return AppConfig(
        global_cfg=GlobalConfig(
            paths=GlobalPathsConfig(ffmpeg="ffmpeg", ffprobe="ffprobe"),
            naming=NamingConfig(index_width=3),
        ),
        project_cfg=ProjectConfig(
            paths=ProjectPathsConfig(output_dir=tmp_path),
            analyze=AnalyzeConfig(
                skip_existing=True,
                texts_subdir="texts",
                compressed_subdir="compressed",
            ),
            script=ScriptConfig(scripts_subdir="scripts"),
            plan=PlanConfig(plans_subdir="plans"),
        ),
        project_dir=tmp_path / "videos",
    )


def _write_text(cfg: AppConfig, name: str, stem: str, index: int) -> Path:
    path = cfg.texts_dir / name
    path.write_text(
        json.dumps(
            {
                "index": index,
                "title": stem,
                "summary": f"summary {stem}",
                "source_file": f"{stem}.mp4",
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_existing_plan(cfg: AppConfig, day_label: str = "day1") -> None:
    plan = {
        "day_title": "Full day",
        "theme": "all",
        "total_estimated_sec": 300,
        "sequence": [
            {"index": "001", "title": "A", "use_timeline": "00:00-00:30"},
            {"index": "002", "title": "B", "use_timeline": "00:00-00:30"},
        ],
    }
    (cfg.plans_dir / f"{day_label}_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (cfg.plans_dir / f"{day_label}_plan.md").write_text("# full", encoding="utf-8")


class TestRunPlanVlogFilesFilter:
    def test_files_selection_bypasses_skip_existing(self, cfg: AppConfig):
        """When files= is set, do not return the full prior plan via skip-existing (I1)."""
        from clio.tasks.plan import run_plan_vlog

        _write_text(cfg, "001_A.json", "A", 1)
        _write_text(cfg, "002_B.json", "B", 2)
        _write_existing_plan(cfg)

        captured: dict = {}

        def _fake_plan(clips, config, day_label="day1", **kwargs):
            captured["clips"] = list(clips)
            return {
                "day_title": "Selected",
                "theme": "subset",
                "total_estimated_sec": 60,
                "sequence": [{"index": c["index"], "title": c["title"], "use_timeline": "00:00-00:10"} for c in clips],
            }

        with patch("clio.tasks.plan.plan_daily_vlog", side_effect=_fake_plan):
            result = run_plan_vlog(cfg, day_label="day1", files=["A"], overwrite=False)

        assert result is not None
        assert "clips" in captured, "plan_daily_vlog should run when files= is set despite existing plan"
        assert len(captured["clips"]) == 1
        assert captured["clips"][0]["title"] == "A"
        assert len(result.get("sequence", [])) == 1
        assert result["sequence"][0]["title"] == "A"

    def test_skip_existing_still_applies_without_files(self, cfg: AppConfig):
        """Without files=, existing valid plan is returned and AI is not called."""
        from clio.tasks.plan import run_plan_vlog

        _write_text(cfg, "001_A.json", "A", 1)
        _write_existing_plan(cfg)

        with patch("clio.tasks.plan.plan_daily_vlog") as mock_plan:
            result = run_plan_vlog(cfg, day_label="day1", files=None, overwrite=False)

        mock_plan.assert_not_called()
        assert result is not None
        assert result["theme"] == "all"
        assert len(result["sequence"]) == 2
