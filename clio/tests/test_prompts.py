from __future__ import annotations

from clio.prompts import load_prompt


def test_load_prompt_uses_project_override(tmp_path):
    prompt_dir = tmp_path / "templates" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "analyze_prompt.md").write_text("project override", encoding="utf-8")

    assert load_prompt("ANALYZE_PROMPT", "default", tmp_path) == "project override"


def test_load_prompt_ignores_empty_override(tmp_path):
    prompt_dir = tmp_path / "templates" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "ANALYZE_PROMPT.md").write_text("  \n", encoding="utf-8")

    assert load_prompt("ANALYZE_PROMPT", "default", tmp_path) == "default"
