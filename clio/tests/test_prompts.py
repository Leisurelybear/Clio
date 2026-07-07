from __future__ import annotations

import pytest

from clio.prompts import load_prompt, render_prompt_template


def test_load_prompt_uses_project_override(tmp_path):
    prompt_dir = tmp_path / "templates" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "analyze_prompt.md").write_text("project override", encoding="utf-8")

    assert load_prompt("ANALYZE_PROMPT", "default", tmp_path) == "project override"


def test_load_prompt_supports_txt_override(tmp_path):
    prompt_dir = tmp_path / "templates" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "ANALYZE_PROMPT.txt").write_text("txt override", encoding="utf-8")

    assert load_prompt("ANALYZE_PROMPT", "default", tmp_path) == "txt override"


def test_load_prompt_ignores_empty_override(tmp_path):
    prompt_dir = tmp_path / "templates" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "ANALYZE_PROMPT.md").write_text("  \n", encoding="utf-8")

    assert load_prompt("ANALYZE_PROMPT", "default", tmp_path) == "default"


def test_render_prompt_template_allows_json_braces():
    template = '返回 JSON: {"index": "{index}", "items": []}'

    result = render_prompt_template("SCRIPT_PROMPT", template, index="001")

    assert result == '返回 JSON: {"index": "001", "items": []}'


def test_render_prompt_template_rejects_unknown_placeholder():
    with pytest.raises(ValueError, match="unknown"):
        render_prompt_template("SCRIPT_PROMPT", "hello {missing}", index="001")
