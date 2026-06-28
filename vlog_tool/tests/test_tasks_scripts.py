from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from vlog_tool.config import AppConfig


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    texts = tmp_path / "texts"
    scripts = tmp_path / "scripts"
    texts.mkdir()
    scripts.mkdir()
    template = tmp_path / "vlog_template.md"
    template.write_text("Template: {title}")
    analyze = MagicMock(skip_existing=True, texts_subdir="texts", compressed_subdir="compressed", max_workers=1)
    script = MagicMock(scripts_subdir="scripts", template_file=template)
    plan = MagicMock(plans_subdir="plans")
    return AppConfig(
        paths=MagicMock(
            input_dir=tmp_path / "videos",
            output_dir=tmp_path,
            ffmpeg="",
            ffprobe="",
        ),
        analyze=analyze,
        script=script,
        plan=plan,
    )


class TestRunGenerateScripts:
    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_creates_output_dir(self, mock_gen, tmp_path):
        texts = tmp_path / "texts"
        texts.mkdir()
        (texts / "001_test.json").write_text('{"title": "t"}')
        scripts = tmp_path / "scripts"
        template = tmp_path / "vlog_template.md"
        template.write_text("Template: {title}")
        cfg = AppConfig(
            paths=MagicMock(output_dir=tmp_path, ffmpeg="", ffprobe=""),
            script=MagicMock(scripts_subdir="scripts", template_file=template),
            analyze=MagicMock(skip_existing=True, texts_subdir="texts", compressed_subdir="compressed", max_workers=1),
            plan=MagicMock(plans_subdir="plans"),
        )
        mock_gen.return_value = {"title": "t", "voiceover": "hello", "edit_tip": ""}

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg)
        assert scripts.is_dir()

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_generates_from_texts(self, mock_gen, cfg):
        data = {"title": "clip1", "scenes": [{"description": "a cat"}]}
        (cfg.texts_dir / "001_test.json").write_text(json.dumps(data))
        mock_gen.return_value = {"title": "clip1", "voiceover": "a cat walks in", "edit_tip": ""}

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg)
        out = cfg.scripts_dir / "001_test_voiceover.json"
        assert out.exists()
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["voiceover"] == "a cat walks in"

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_skip_existing(self, mock_gen, cfg):
        data = {"title": "t"}
        (cfg.texts_dir / "001.json").write_text(json.dumps(data))
        out = cfg.scripts_dir / "001_voiceover.json"
        out.write_text('{"voiceover": "existing"}')

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg)
        mock_gen.assert_not_called()

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_writes_md_file(self, mock_gen, cfg):
        data = {"title": "clip1", "scenes": []}
        (cfg.texts_dir / "001_test.json").write_text(json.dumps(data))
        mock_gen.return_value = {"title": "clip1", "voiceover": "hello world", "edit_tip": "add b-roll"}

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg)
        md = cfg.scripts_dir / "001_test_voiceover.md"
        assert md.exists()
        content = md.read_text(encoding="utf-8")
        assert "hello world" in content
        assert "add b-roll" in content

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_single_file_param(self, mock_gen, cfg):
        data = {"title": "t"}
        f = cfg.texts_dir / "001.json"
        f.write_text(json.dumps(data))
        mock_gen.return_value = {"title": "t", "voiceover": "v", "edit_tip": ""}

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg, single_file=f)
        out = cfg.scripts_dir / "001_voiceover.json"
        assert out.exists()

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_passes_template(self, mock_gen, cfg):
        data = {"title": "t"}
        (cfg.texts_dir / "001.json").write_text(json.dumps(data))
        mock_gen.return_value = {"title": "t", "voiceover": "v", "edit_tip": ""}

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg)
        assert "Template: {title}" in mock_gen.call_args.args[1]

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_tracker_next_called(self, mock_gen, cfg):
        data = {"title": "t"}
        (cfg.texts_dir / "001.json").write_text(json.dumps(data))
        mock_gen.return_value = {"title": "t", "voiceover": "v", "edit_tip": ""}
        tracker = MagicMock()

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg, tracker=tracker)
        tracker.update.assert_called_once()
        tracker.next.assert_called_once()
        tracker.log.assert_called_once()

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_no_texts_found(self, mock_gen, cfg):
        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg)
        mock_gen.assert_not_called()

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_files_filter(self, mock_gen, cfg):
        data = {"title": "t", "scenes": []}
        for name in ("001_A.json", "002_B.json", "003_C.json"):
            (cfg.texts_dir / name).write_text(json.dumps(data))
        mock_gen.return_value = {"title": "t", "voiceover": "v", "edit_tip": ""}

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg, files=["002_B"])
        assert mock_gen.call_count == 1
        out = cfg.scripts_dir / "002_B_voiceover.json"
        assert out.exists()

    @patch("vlog_tool.tasks.scripts.generate_voiceover")
    def test_overwrite_flag(self, mock_gen, cfg):
        data = {"title": "t"}
        (cfg.texts_dir / "001.json").write_text(json.dumps(data))
        out = cfg.scripts_dir / "001_voiceover.json"
        out.write_text('{"voiceover": "existing"}')
        mock_gen.return_value = {"title": "t", "voiceover": "new", "edit_tip": ""}

        from vlog_tool.tasks.scripts import run_generate_scripts

        run_generate_scripts(cfg, overwrite=True)
        assert mock_gen.call_count == 1
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["voiceover"] == "new"
