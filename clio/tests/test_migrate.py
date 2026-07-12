"""Tests for clio.tasks.migrate — legacy project → videos.json migration."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from clio.tasks.migrate import run_migrate


def _write_legacy_project(root: Path, name: str = "trip1") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "GL010001.MP4").write_bytes(b"video1")
    (root / "GL010002.MP4").write_bytes(b"video2")
    (root / "project.yaml").write_text(
        yaml.dump(
            {
                "paths": {
                    "input_dir": ".",
                    "output_dir": "./output",
                    "recursive": True,
                },
                "ai": {"context": ""},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (root / "project.json").write_text(
        json.dumps({"name": name, "output_dir": str(root / "output"), "currentDay": "day1"}),
        encoding="utf-8",
    )
    return root


def test_migrate_in_place(tmp_path: Path) -> None:
    project = _write_legacy_project(tmp_path / "trip1")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("paths: {}\n", encoding="utf-8")
    reg = tmp_path / "projects.json"
    reg.write_text(json.dumps({"projects": [str(project)]}), encoding="utf-8")

    updated, errors = run_migrate(config_path, from_path=project)
    assert updated == 1, errors
    assert (project / "videos.json").is_file()
    videos = json.loads((project / "videos.json").read_text(encoding="utf-8"))
    assert len(videos) == 2
    raw = yaml.safe_load((project / "project.yaml").read_text(encoding="utf-8"))
    assert "input_dir" not in (raw.get("paths") or {})
    assert "recursive" not in (raw.get("paths") or {})
    assert (project / "project.yaml.migrate-bak").is_file()
    data = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert data.get("version") == 2


def test_migrate_skips_already_new(tmp_path: Path) -> None:
    project = tmp_path / "newproj"
    project.mkdir()
    (project / "project.yaml").write_text(
        yaml.dump({"paths": {"output_dir": "./output"}}, allow_unicode=True),
        encoding="utf-8",
    )
    (project / "videos.json").write_text("[]", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("paths: {}\n", encoding="utf-8")

    updated, _errors = run_migrate(config_path, from_path=project)
    assert updated == 0
