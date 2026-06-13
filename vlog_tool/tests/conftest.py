"""Shared pytest fixtures for all test modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from vlog_tool.config import AppConfig, ProviderConfig, ProxyConfig, load_config


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
        "      api_key: test-gemini-key\n"
        "    deepseek:\n"
        "      type: openai\n"
        "      api_key: test-deepseek-key\n"
        "      base_url: https://api.deepseek.com/v1\n"
        "  tasks:\n"
        "    video_analyze:\n"
        "      provider: gemini\n"
        "      model: gemini-2.5-flash\n"
        "    voiceover:\n"
        "      provider: deepseek\n"
        "      model: deepseek-chat\n"
        "    vlog_plan:\n"
        "      provider: deepseek\n"
        "      model: deepseek-chat\n"
        "compress:\n"
        "  target_size_mb: 5\n"
        "  max_width: 640\n"
        "  fps: 15\n"
        "  remove_audio: true\n"
        "  split_max_min: 15\n"
        "  splits_subdir: splits\n",
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
        "    deepseek:\n"
        "      type: openai\n"
        "      api_key_env: DEEPSEEK_API_KEY\n"
        "      base_url: https://api.deepseek.com/v1\n"
        "  tasks:\n"
        "    video_analyze:\n"
        "      provider: gemini\n"
        "      model: gemini-2.5-flash\n"
        "    voiceover:\n"
        "      provider: deepseek\n"
        "      model: deepseek-chat\n"
        "compress:\n"
        "  target_size_mb: 5\n"
    )


@pytest.fixture
def loaded_config(tmp_config: Path) -> AppConfig:
    """Load a full AppConfig from a tmp_config."""
    return load_config(tmp_config / "config.yaml")


@pytest.fixture
def gemini_provider_cfg(loaded_config: AppConfig) -> ProviderConfig:
    """Extract the gemini provider config from a loaded config."""
    return loaded_config.ai.providers["gemini"]


@pytest.fixture
def proxy_cfg() -> ProxyConfig:
    """Return a disabled proxy config."""
    return ProxyConfig(enabled=False, url="")

