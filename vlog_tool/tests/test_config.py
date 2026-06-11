"""Tests for vlog_tool/config.py — pure functions and config loading."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from vlog_tool.config import (
    AppConfig,
    _load_context,
    _path,
    _resolve_api_key,
    _validate_config,
    deep_merge,
    load_config,
)

if TYPE_CHECKING:
    from vlog_tool.config import AIConfig, PathsConfig

# ── deep_merge ──────────────────────────────────────────────────────


class TestDeepMerge:
    def test_basic_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 99}
        assert deep_merge(base, override) == {"a": 1, "b": 99}

    def test_nested_dict_merge(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 999, "z": 4}}
        result = deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 999, "z": 4}, "b": 3}

    def test_new_keys_from_override(self):
        base = {"a": 1}
        override = {"b": 2}
        assert deep_merge(base, override) == {"a": 1, "b": 2}

    def test_non_dict_override(self):
        base = {"a": {"nested": "keep"}}
        override = {"a": "replace"}
        assert deep_merge(base, override) == {"a": "replace"}

    def test_none_override(self):
        base = {"a": 1, "b": 2}
        override = {"a": None}
        assert deep_merge(base, override) == {"a": None, "b": 2}

    def test_empty_override(self):
        base = {"a": 1}
        assert deep_merge(base, {}) == {"a": 1}

    def test_empty_base(self):
        assert deep_merge({}, {"a": 1}) == {"a": 1}

    def test_deeply_nested(self):
        base = {"one": {"two": {"three": 3}}}
        override = {"one": {"two": {"three": 99, "four": 4}}}
        result = deep_merge(base, override)
        assert result == {"one": {"two": {"three": 99, "four": 4}}}

    def test_does_not_mutate_inputs(self):
        base = {"a": {"b": 1}}
        override = {"a": {"b": 2}}
        deep_merge(base, override)
        assert base == {"a": {"b": 1}}
        assert override == {"a": {"b": 2}}

    def test_list_replaced_not_merged(self):
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        assert deep_merge(base, override) == {"items": [4, 5]}


# ── _path ───────────────────────────────────────────────────────────


class TestPath:
    def test_none_returns_dot(self):
        # _path(None) returns unresolved Path(".")
        assert str(_path(None)) == "."

    def test_empty_returns_dot(self):
        assert str(_path("")) == "."

    def test_absolute_path(self):
        result = _path("/some/absolute/path")
        assert result == Path("/some/absolute/path").resolve()

    def test_relative_with_base(self):
        base = Path("/base")
        result = _path("sub/file.txt", base)
        assert result == (base / "sub/file.txt").resolve()

    def test_relative_without_base(self):
        result = _path("relative/path")
        assert result == Path("relative/path").resolve()


# ── _resolve_api_key ───────────────────────────────────────────────


class TestResolveApiKey:
    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "env_value")
        raw = {"api_key_env": "MY_KEY", "api_key": "inline_value"}
        assert _resolve_api_key(raw) == "env_value"

    def test_env_var_missing_falls_to_inline(self):
        raw = {"api_key_env": "NONEXISTENT_VAR", "api_key": "inline_value"}
        assert _resolve_api_key(raw) == "inline_value"

    def test_no_env_var_returns_inline(self):
        raw = {"api_key": "direct_key"}
        assert _resolve_api_key(raw) == "direct_key"

    def test_empty_env_name_returns_inline(self):
        raw = {"api_key_env": "", "api_key": "fallback"}
        assert _resolve_api_key(raw) == "fallback"


# ── _load_context ──────────────────────────────────────────────────


class TestLoadContext:
    def test_inline_takes_priority(self, tmp_path):
        ai_raw = {"context": "inline text", "context_file": "ignored.md"}
        assert _load_context(ai_raw, tmp_path) == "inline text"

    def test_context_file_resolved_from_base(self, tmp_path):
        ctx_file = tmp_path / "mycontext.md"
        ctx_file.write_text("file content", encoding="utf-8")
        ai_raw = {"context_file": "mycontext.md"}
        assert _load_context(ai_raw, tmp_path) == "file content"

    def test_context_file_from_project_dir_first(self, tmp_path):
        base = tmp_path / "config_dir"
        base.mkdir()
        proj = tmp_path / "project_dir"
        proj.mkdir()
        (proj / "ctx.md").write_text("project context", encoding="utf-8")

        ai_raw = {"context_file": "ctx.md"}
        result = _load_context(ai_raw, base, project_dir=proj)
        assert result == "project context"

    def test_fallback_to_base_when_not_in_project(self, tmp_path):
        base = tmp_path / "config_dir"
        base.mkdir()
        (base / "ctx.md").write_text("base context", encoding="utf-8")

        ai_raw = {"context_file": "ctx.md"}
        result = _load_context(ai_raw, base, project_dir=tmp_path / "nonexistent")
        assert result == "base context"

    def test_missing_file_returns_empty(self, tmp_path):
        ai_raw = {"context_file": "does_not_exist.md"}
        assert _load_context(ai_raw, tmp_path) == ""

    def test_no_context_configured(self, tmp_path):
        assert _load_context({}, tmp_path) == ""


# ── _validate_config ────────────────────────────────────────────────


class TestValidateConfig:
    def test_valid_config_passes(self):
        cfg = AppConfig(
            paths=create_paths(),
            ai=create_ai(providers={"gemini": "gemini"}, tasks={"task": ("gemini", "m")}),
        )
        _validate_config(cfg)  # should not raise

    def test_proxy_enabled_no_url_raises(self):
        from vlog_tool.config import ProxyConfig

        cfg = AppConfig(
            paths=create_paths(),
            ai=create_ai(),
            proxy=ProxyConfig(enabled=True, url=""),
        )
        with pytest.raises(ValueError, match="proxy"):
            _validate_config(cfg)

    def test_task_refers_to_nonexistent_provider(self):
        cfg = AppConfig(
            paths=create_paths(),
            ai=create_ai(
                providers={"gemini": "gemini"},
                tasks={"task": ("nonexistent", "m")},
            ),
        )
        with pytest.raises(ValueError, match="task"):
            _validate_config(cfg)

    def test_empty_provider_set_with_task(self):
        cfg = AppConfig(
            paths=create_paths(),
            ai=create_ai(
                providers={},
                tasks={"task": ("some_provider", "m")},
            ),
        )
        with pytest.raises(ValueError, match="<无>"):
            _validate_config(cfg)


# ── load_config ─────────────────────────────────────────────────────


class TestLoadConfig:
    def test_minimal_config(self, tmp_config):
        cfg = load_config(tmp_config / "config.yaml")
        assert isinstance(cfg, AppConfig)
        assert cfg.compress.fps == 15
        assert cfg.compress.target_size_mb == 5
        assert cfg.proxy.enabled is False

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_with_project_dir_no_project_yaml(self, tmp_config):
        """project_dir without project.yaml returns base config."""
        cfg = load_config(tmp_config / "config.yaml", project_dir=tmp_config)
        assert cfg.compress.fps == 15

    def test_with_project_dir_and_project_yaml(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "compress:\n  fps: 15\n  target_size_mb: 5\nproxy:\n  enabled: false\n",
            encoding="utf-8",
        )
        proj_yaml = tmp_path / "project.yaml"
        proj_yaml.write_text("compress:\n  fps: 30\n", encoding="utf-8")

        cfg = load_config(cfg_path, project_dir=tmp_path)
        assert cfg.compress.fps == 30  # overridden
        assert cfg.compress.target_size_mb == 5  # inherited

    def test_project_context_file_resolved_correctly(self, tmp_path):
        """context_file in project.yaml resolves relative to project_dir."""
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(
            "ai:\n  providers:\n    g:\n      type: gemini\n      api_key: k\n"
            "  tasks:\n    t:\n      provider: g\n      model: m\n"
            "proxy:\n  enabled: false\n",
            encoding="utf-8",
        )
        proj_dir = tmp_path / "project"
        proj_dir.mkdir()
        (proj_dir / "ctx.md").write_text("project specific", encoding="utf-8")
        (proj_dir / "project.yaml").write_text("ai:\n  context_file: ctx.md\n", encoding="utf-8")

        cfg = load_config(cfg_path, project_dir=proj_dir)
        assert cfg.ai.context == "project specific"


# ── Helpers ─────────────────────────────────────────────────────────


def create_paths(**kwargs) -> PathsConfig:
    """Helper to build a PathsConfig with defaults."""
    from vlog_tool.config import PathsConfig

    defaults = {"input_dir": Path("."), "output_dir": Path("./output")}
    return PathsConfig(**{**defaults, **kwargs})


def create_ai(
    providers: dict[str, str] | None = None,
    tasks: dict[str, tuple[str, str]] | None = None,
    context: str = "",
) -> AIConfig:
    """Helper to build an AIConfig with provider/task data class objects."""
    from vlog_tool.config import AIConfig, ProviderConfig, TaskConfig

    ai = AIConfig(context=context)
    if providers:
        for name, ptype in providers.items():
            ai.providers[name] = ProviderConfig(name=name, type=ptype, api_key="k")
    if tasks:
        for name, (provider, model) in tasks.items():
            ai.tasks[name] = TaskConfig(provider=provider, model=model)
    return ai
