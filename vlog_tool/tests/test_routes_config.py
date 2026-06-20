"""Tests for vlog_tool/ui/routes/config_routes.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml

from vlog_tool.ui.routes.config_routes import (
    handle_get_config,
    handle_get_config_raw,
    handle_post_config_init,
    handle_put_config_raw,
)


class TestHandleGetConfig:
    def test_basic(self, tmp_path: Path):
        handler = MagicMock()
        proj_input = tmp_path / "input"
        proj_input.mkdir()
        proj_out = tmp_path / "output"
        proj_out.mkdir()
        handler._resolve_project_input.return_value = proj_input
        handler._get_project_output.return_value = proj_out
        handler._send_json = MagicMock()

        handle_get_config(handler, {})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        payload = args[0][0]
        assert "input_dir" in payload
        assert "output_dir" in payload
        assert "compressed_dir" in payload


class TestHandleGetConfigRaw:
    def test_needs_init(self, tmp_path: Path):
        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.write_bytes(b"key: val\n")
        # Without project.yaml in a non-default project dir
        proj_input = tmp_path / "custom_project"
        proj_input.mkdir()
        default_input = tmp_path / "input"
        default_input.mkdir()

        handler.config_path = cfg
        handler.input_dir = default_input
        handler._resolve_project_input.return_value = proj_input
        handler._send_json = MagicMock()

        handle_get_config_raw(handler, {})

        handler._send_json.assert_called_once_with({"needs_init": True})

    def test_returns_merged_config(self, tmp_path: Path):
        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.dump({"compress": {"target_size_mb": 5, "max_width": 640}}), encoding="utf-8")
        proj_input = tmp_path / "default"
        proj_input.mkdir()

        handler.config_path = cfg
        handler.input_dir = proj_input
        handler._resolve_project_input.return_value = proj_input
        handler._send_json = MagicMock()

        handle_get_config_raw(handler, {})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        payload = args[0][0]
        assert payload["compress"]["target_size_mb"] == 5
        assert payload.get("_config_source") == "global_fallback"
        # Default ai.context should be set
        assert payload.get("ai", {}).get("context") == ""


class TestHandlePostConfigInit:
    def test_default_project_no_init_needed(self, tmp_path: Path):
        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.write_bytes(b"")
        proj_input = tmp_path / "input"

        handler.config_path = cfg
        handler.input_dir = proj_input
        handler._resolve_project_input.return_value = proj_input
        handler._send_json = MagicMock()
        handler.__class__._config_cache = MagicMock()

        handle_post_config_init(handler, {}, {})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][1] == 400


class TestHandlePutConfigRaw:
    def test_no_config_path(self):
        handler = MagicMock()
        handler.config_path = None
        handler._send_json = MagicMock()
        handle_put_config_raw(handler, {}, {"test": True})
        handler._send_json.assert_called_once_with({"ok": False, "error": "config_path not available"}, 500)

    def test_put_project_config(self, tmp_path: Path):
        """Writing to a non-default project directory stores in project.yaml."""
        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.parent.mkdir(exist_ok=True)
        cfg.write_text(yaml.dump({"paths": {"input_dir": "./input", "output_dir": "./output"}}), encoding="utf-8")
        proj_input = tmp_path / "custom"
        proj_input.mkdir()

        handler.config_path = cfg
        handler.input_dir = tmp_path
        handler._resolve_project_input.return_value = proj_input
        handler.__class__._config_cache = MagicMock()
        handler._send_json = MagicMock()

        handle_put_config_raw(handler, {}, {"compress": {"target_size_mb": 10}})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][0]["ok"] is True
        proj_yaml = proj_input / "project.yaml"
        assert proj_yaml.is_file()
        data = yaml.safe_load(proj_yaml.read_text(encoding="utf-8"))
        assert data["compress"]["target_size_mb"] == 10

    def test_put_global_validation_failure_backup(self, tmp_path: Path):
        """Invalid config (proxy.enabled without url) restores original."""
        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "paths": {"input_dir": "./in", "output_dir": "./out"},
                    "proxy": {"enabled": False, "url": ""},
                }
            ),
            encoding="utf-8",
        )

        handler.config_path = cfg
        handler.input_dir = tmp_path
        handler._resolve_project_input.return_value = tmp_path
        handler.__class__._config_cache = MagicMock()
        handler._send_json = MagicMock()

        # Send config with proxy.enabled=true but no url (fails validation)
        handle_put_config_raw(handler, {}, {"proxy": {"enabled": True, "url": ""}})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][0]["ok"] is False
        # Original content preserved
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert data["proxy"]["enabled"] is False

    def test_put_config_coerces_types(self, tmp_path: Path):
        """Values are coerced to match reference config types."""
        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "paths": {"input_dir": "./in", "output_dir": "./out"},
                    "compress": {"target_size_mb": 5, "max_width": 640},
                }
            ),
            encoding="utf-8",
        )

        handler.config_path = cfg
        handler.input_dir = tmp_path
        handler._resolve_project_input.return_value = tmp_path
        handler.__class__._config_cache = MagicMock()
        handler._send_json = MagicMock()

        # Send string "10" that should be coerced to int via ref_raw type
        handle_put_config_raw(handler, {}, {"compress": {"target_size_mb": "10"}})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][0]["ok"] is True
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        assert isinstance(data["compress"]["target_size_mb"], (int, float))

    def test_put_config_includes_descriptions_in_raw_response(self, tmp_path: Path):
        """handle_get_config_raw response includes _descriptions field."""
        from vlog_tool.config.descriptions import CONFIG_DESCRIPTIONS

        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.dump({"compress": {"target_size_mb": 5}}), encoding="utf-8")
        proj_input = tmp_path / "default"
        proj_input.mkdir()

        handler.config_path = cfg
        handler.input_dir = proj_input
        handler._resolve_project_input.return_value = proj_input
        handler._send_json = MagicMock()

        handle_get_config_raw(handler, {})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        payload = args[0][0]
        assert "_descriptions" in payload
        assert payload["_descriptions"]["compress.target_size_mb"] == CONFIG_DESCRIPTIONS["compress.target_size_mb"]

    def test_post_config_init_creates_project_yaml(self, tmp_path: Path):
        """handle_post_config_init creates valid project.yaml for non-default project."""
        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            yaml.dump({"paths": {"input_dir": "./input", "output_dir": "./output"}, "compress": {"target_size_mb": 5}}),
            encoding="utf-8",
        )
        proj_input = tmp_path / "custom"
        proj_input.mkdir()

        handler.config_path = cfg
        handler.input_dir = tmp_path
        handler._resolve_project_input.return_value = proj_input
        handler._send_json = MagicMock()
        handler.__class__._config_cache = MagicMock()

        handle_post_config_init(handler, {}, {})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][0]["ok"] is True
        proj_yaml = proj_input / "project.yaml"
        assert proj_yaml.is_file()
        data = yaml.safe_load(proj_yaml.read_text(encoding="utf-8"))
        assert data["compress"]["target_size_mb"] == 5

    def test_post_config_init_rejects_default(self, tmp_path: Path):
        """Default project cannot be initialized with project.yaml."""
        handler = MagicMock()
        cfg = tmp_path / "config.yaml"
        cfg.write_bytes(b"")
        proj_input = tmp_path / "input"
        proj_input.mkdir()

        handler.config_path = cfg
        handler.input_dir = proj_input
        handler._resolve_project_input.return_value = proj_input
        handler._send_json = MagicMock()
        handler.__class__._config_cache = MagicMock()

        handle_post_config_init(handler, {}, {})

        handler._send_json.assert_called_once()
        args = handler._send_json.call_args
        assert args[0][1] == 400
