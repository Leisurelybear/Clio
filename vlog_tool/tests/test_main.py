"""Tests for main.py CLI subcommands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from main import main

MINIMAL_CONFIG = """\
paths:
  input_dir: .
  output_dir: ./output
  logs_dir: ./logs
proxy:
  enabled: false
ai:
  context: ''
  providers:
    gemini:
      type: gemini
      api_key: test-gemini-key
    deepseek:
      type: openai
      api_key: test-deepseek-key
      base_url: https://api.deepseek.com/v1
  tasks:
    video_analyze:
      provider: gemini
      model: gemini-2.5-flash
    voiceover:
      provider: deepseek
      model: deepseek-chat
    vlog_plan:
      provider: deepseek
      model: deepseek-chat
compress:
  target_size_mb: 5
  max_width: 640
  fps: 15
  remove_audio: true
  split_max_min: 15
  splits_subdir: splits
whisper:
  enabled: true
  model_size: small
  language: zh
  device: cpu
  transcripts_subdir: transcripts
"""


@pytest.fixture(autouse=True)
def _mock_whisper_deps():
    """Mock faster_whisper import so CLI imports work."""
    fake_fw = MagicMock()
    fake_fw.__version__ = "1.0.0"
    with patch.dict("sys.modules", {"faster_whisper": fake_fw}):
        yield


@pytest.fixture
def cli_runner():
    def _run(args):
        try:
            return main(args)
        except SystemExit as e:
            return e.code

    return _run


@pytest.fixture
def config_path(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(MINIMAL_CONFIG, encoding="utf-8")
    return cfg


def test_transcribe_subcommand(cli_runner, config_path):
    result = cli_runner(["--config", str(config_path), "transcribe"])
    assert result == 0


def test_whisper_help(cli_runner, config_path):
    result = cli_runner(["--config", str(config_path), "whisper", "--help"])
    assert result == 0


def test_whisper_check_subcommand(cli_runner, config_path):
    result = cli_runner(["--config", str(config_path), "whisper", "check"])
    assert result == 0


@patch("vlog_tool.pipeline.run_plan_vlog")
def test_plan_no_transcripts_flag(mock_run_plan, cli_runner, config_path, tmp_path):
    """--no-transcripts 应设置 config.plan.use_transcripts=False"""
    result = cli_runner(["--config", str(config_path), "plan", "--no-transcripts"])
    assert result == 0
    cfg_arg = mock_run_plan.call_args[0][0]
    assert cfg_arg.plan.use_transcripts is False
