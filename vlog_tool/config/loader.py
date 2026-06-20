from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from vlog_tool.config.models import (
    AIConfig,
    AnalyzeConfig,
    AppConfig,
    CompressConfig,
    NamingConfig,
    PathsConfig,
    PlanConfig,
    ProviderConfig,
    ProxyConfig,
    ScriptConfig,
    TaskConfig,
)
from vlog_tool.config.parsers import (
    _parse_providers,
    _parse_tasks,
    _parse_whisper,
)
from vlog_tool.config.validators import _filter_dc, _validate_config


def _path(value: str | None, base: Path | None = None) -> Path:
    if not value:
        raise ValueError("路径不能为空")
    path = Path(value)
    if base and not path.is_absolute():
        return (base / path).resolve()
    return path.resolve()


def _load_dotenv(base: Path) -> None:
    env_file = base / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def deep_merge(base: dict, override: dict) -> dict:
    result = {}
    for key in base:
        if key in override:
            if isinstance(base[key], dict) and isinstance(override[key], dict):
                result[key] = deep_merge(base[key], override[key])
            else:
                result[key] = override[key]
        else:
            result[key] = base[key]
    for key in override:
        if key not in base:
            result[key] = override[key]
    return result


def _load_context(ai_raw: dict, base: Path, project_dir: Path | None = None) -> str:
    inline = (ai_raw.get("context") or "").strip()
    if inline:
        return inline
    file_ref = (ai_raw.get("context_file") or "").strip()
    if not file_ref:
        return ""
    if project_dir is not None:
        path = _path(file_ref, project_dir)
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    path = _path(file_ref, base)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _legacy_ai_config(raw: dict) -> AIConfig:
    gemini_raw = raw.get("gemini", {})
    api_key = os.environ.get("GEMINI_API_KEY") or gemini_raw.get("api_key", "")
    model = gemini_raw.get("model", "gemini-2.5-flash")
    return AIConfig(
        providers={
            "gemini": ProviderConfig(
                name="gemini",
                type="gemini",
                api_key=api_key,
                api_key_env="GEMINI_API_KEY",
                poll_interval_sec=gemini_raw.get("poll_interval_sec", 5),
            ),
        },
        tasks={
            "video_analyze": TaskConfig(provider="gemini", model=model),
            "voiceover": TaskConfig(provider="gemini", model=model),
            "vlog_plan": TaskConfig(provider="gemini", model=model),
        },
    )


def load_config(
    config_path: str | Path = "config.yaml",
    project_dir: Path | None = None,
) -> AppConfig:
    config_file = Path(config_path).resolve()
    base = config_file.parent
    _load_dotenv(base)

    with config_file.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    if project_dir is not None:
        project_yaml = Path(project_dir).resolve() / "project.yaml"
        if project_yaml.is_file():
            with project_yaml.open(encoding="utf-8") as f:
                project_raw: dict[str, Any] = yaml.safe_load(f) or {}
            raw = deep_merge(raw, project_raw)

    paths_raw = raw.get("paths", {})
    ai_raw = raw.get("ai")

    if ai_raw:
        ai = AIConfig(
            providers=_parse_providers(ai_raw.get("providers")),
            tasks=_parse_tasks(ai_raw.get("tasks")),
            context=_load_context(ai_raw, base, project_dir=project_dir),
        )
    else:
        ai = _legacy_ai_config(raw)

    config = AppConfig(
        paths=PathsConfig(
            input_dir=_path(paths_raw.get("input_dir", "."), base),
            output_dir=_path(paths_raw.get("output_dir", "./output"), base),
            ffmpeg=paths_raw.get("ffmpeg", ""),
            ffprobe=paths_raw.get("ffprobe", ""),
            recursive=paths_raw.get("recursive", False),
            logs_dir=_path(paths_raw.get("logs_dir", "./logs"), base),
        ),
        proxy=ProxyConfig(**_filter_dc(raw.get("proxy", {}), ProxyConfig)),
        ai=ai,
        compress=CompressConfig(**_filter_dc(raw.get("compress", {}), CompressConfig)),
        analyze=AnalyzeConfig(**_filter_dc(raw.get("analyze", {}), AnalyzeConfig)),
        naming=NamingConfig(**_filter_dc(raw.get("naming", {}), NamingConfig)),
        script=ScriptConfig(
            scripts_subdir=raw.get("script", {}).get("scripts_subdir", "scripts"),
            template_file=_path(
                raw.get("script", {}).get("template_file", "./templates/vlog_template.md"),
                base,
            ),
            target_words=raw.get("script", {}).get("target_words", 80),
        ),
        plan=PlanConfig(**_filter_dc(raw.get("plan", {}), PlanConfig)),
        whisper=_parse_whisper(raw.get("whisper", {})),
    )
    _validate_config(config)
    return config


def apply_run_paths(
    config: AppConfig,
    input_dir: Path | None = None,
    output_dir: Path | None = None,
    output_by_input_name: bool = True,
) -> AppConfig:
    config = deepcopy(config)
    if input_dir:
        config.paths.input_dir = input_dir.resolve()
    if output_dir:
        config.paths.output_dir = output_dir.resolve()
    elif input_dir and output_by_input_name:
        config.paths.output_dir = (config.paths.output_dir / input_dir.name).resolve()
    return config
