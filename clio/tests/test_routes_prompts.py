from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from clio.ui.routes.prompts import handle_get_prompts, handle_put_prompt


def test_handle_get_prompts_lists_defaults(tmp_path: Path):
    handler = MagicMock()
    handler._resolve_project_input.return_value = tmp_path

    handle_get_prompts(handler, {})

    payload = handler._send_json.call_args.args[0]
    names = {item["name"] for item in payload["prompts"]}
    assert "ANALYZE_PROMPT" in names
    assert payload["override_dir"] == str(tmp_path / "templates" / "prompts")


def test_handle_get_prompts_uses_project_override(tmp_path: Path):
    prompt_dir = tmp_path / "templates" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "ANALYZE_PROMPT.md").write_text("project prompt", encoding="utf-8")
    handler = MagicMock()
    handler._resolve_project_input.return_value = tmp_path

    handle_get_prompts(handler, {})

    payload = handler._send_json.call_args.args[0]
    item = next(p for p in payload["prompts"] if p["name"] == "ANALYZE_PROMPT")
    assert item["content"] == "project prompt"
    assert item["override"] == "project prompt"
    assert item["has_override"] is True


def test_handle_put_prompt_saves_project_override(tmp_path: Path):
    handler = MagicMock()
    handler._resolve_project_input.return_value = tmp_path

    handle_put_prompt(handler, {}, {"content": "custom prompt"}, "analyze_prompt")

    saved = tmp_path / "templates" / "prompts" / "ANALYZE_PROMPT.md"
    assert saved.read_text(encoding="utf-8") == "custom prompt"
    handler._send_json.assert_called_once()
    payload = handler._send_json.call_args.args[0]
    assert payload["ok"] is True
    assert payload["name"] == "ANALYZE_PROMPT"


def test_handle_put_prompt_rejects_unknown_name(tmp_path: Path):
    handler = MagicMock()
    handler._resolve_project_input.return_value = tmp_path

    handle_put_prompt(handler, {}, {"content": "x"}, "../secret")

    handler._send_json.assert_called_once_with({"ok": False, "error": "unknown prompt"}, 404)


def test_handle_put_prompt_rejects_empty_content(tmp_path: Path):
    handler = MagicMock()
    handler._resolve_project_input.return_value = tmp_path

    handle_put_prompt(handler, {}, {"content": "  "}, "ANALYZE_PROMPT")

    handler._send_json.assert_called_once_with({"ok": False, "error": "content cannot be empty"}, 400)
