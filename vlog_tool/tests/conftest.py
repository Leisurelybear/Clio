"""Shared pytest fixtures for all test modules."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Create a minimal config.yaml at tmp_path and return its path."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "paths:\n"
        "  input_dir: .\n"
        "  output_dir: ./output\n"
        "  logs_dir: ./logs\n"
        "proxy:\n"
        "  enabled: false\n"
        "ai:\n"
        "  context: ''\n"
        "  providers:\n"
        "    gemini:\n"
        "      type: gemini\n"
        "      api_key_env: GEMINI_API_KEY\n"
        "  tasks:\n"
        "    video_analyze:\n"
        "      provider: gemini\n"
        "      model: gemini-2.5-flash\n"
        "    voiceover:\n"
        "      provider: gemini\n"
        "      model: gemini-2.5-flash\n"
        "    vlog_plan:\n"
        "      provider: gemini\n"
        "      model: gemini-2.5-flash\n"
        "compress:\n"
        "  target_size_mb: 5\n"
        "  max_width: 640\n"
        "  fps: 15\n"
        "  remove_audio: true\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    """Return a clean temp directory."""
    return tmp_path


@pytest.fixture
def config_yaml_content() -> str:
    """Return the standard config.yaml content as a string."""
    return (
        "paths:\n"
        "  input_dir: .\n"
        "  output_dir: ./output\n"
        "proxy:\n"
        "  enabled: false\n"
        "ai:\n"
        "  context: test context\n"
        "  providers:\n"
        "    gemini:\n"
        "      type: gemini\n"
        "      api_key_env: GEMINI_API_KEY\n"
        "  tasks:\n"
        "    video_analyze:\n"
        "      provider: gemini\n"
        "      model: gemini-2.5-flash\n"
        "compress:\n"
        "  target_size_mb: 5\n"
    )
