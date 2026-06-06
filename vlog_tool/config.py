from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PathsConfig:
    input_dir: Path
    output_dir: Path
    ffmpeg: str = ""
    ffprobe: str = ""
    recursive: bool = False
    logs_dir: Path = Path("./logs")


@dataclass
class ProxyConfig:
    enabled: bool = False
    url: str = ""


@dataclass
class ProviderConfig:
    name: str
    type: str
    api_key: str = ""
    api_key_env: str = ""
    base_url: str = ""
    poll_interval_sec: int = 5


@dataclass
class TaskConfig:
    provider: str
    model: str


@dataclass
class AIConfig:
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    tasks: dict[str, TaskConfig] = field(default_factory=dict)
    context: str = ""  # 内容会作为"前言"注入到所有 AI 提示词


@dataclass
class CompressConfig:
    target_size_mb: float = 5
    max_width: int = 640
    fps: int = 15
    codec: str = "libx264"
    crf: int = 32
    remove_audio: bool = True


@dataclass
class AnalyzeConfig:
    compressed_subdir: str = "compressed"
    texts_subdir: str = "texts"
    skip_existing: bool = True


@dataclass
class NamingConfig:
    index_width: int = 3


@dataclass
class ScriptConfig:
    scripts_subdir: str = "scripts"
    template_file: Path = Path("./templates/vlog_template.md")
    target_words: int = 80


@dataclass
class PlanConfig:
    plans_subdir: str = "plans"
    max_clips_per_day: int = 12
    target_duration_sec: int = 180


@dataclass
class AppConfig:
    paths: PathsConfig
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    compress: CompressConfig = field(default_factory=CompressConfig)
    analyze: AnalyzeConfig = field(default_factory=AnalyzeConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    script: ScriptConfig = field(default_factory=ScriptConfig)
    plan: PlanConfig = field(default_factory=PlanConfig)

    @property
    def compressed_dir(self) -> Path:
        return self.paths.output_dir / self.analyze.compressed_subdir

    @property
    def texts_dir(self) -> Path:
        return self.paths.output_dir / self.analyze.texts_subdir

    @property
    def scripts_dir(self) -> Path:
        return self.paths.output_dir / self.script.scripts_subdir

    @property
    def plans_dir(self) -> Path:
        return self.paths.output_dir / self.plan.plans_subdir

    @property
    def summary_csv(self) -> Path:
        return self.paths.output_dir / "summary.csv"


def _path(value: str | None, base: Path | None = None) -> Path:
    if not value:
        return Path(".")
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


def _resolve_api_key(provider_raw: dict) -> str:
    env_name = provider_raw.get("api_key_env", "")
    if env_name:
        env_val = os.environ.get(env_name, "")
        if env_val:
            return env_val
    return provider_raw.get("api_key", "")


def _parse_providers(raw: dict) -> dict[str, ProviderConfig]:
    providers: dict[str, ProviderConfig] = {}
    for name, cfg in (raw or {}).items():
        providers[name] = ProviderConfig(
            name=name,
            type=cfg.get("type", "gemini"),
            api_key=_resolve_api_key(cfg),
            api_key_env=cfg.get("api_key_env", ""),
            base_url=cfg.get("base_url", ""),
            poll_interval_sec=cfg.get("poll_interval_sec", 5),
        )
    return providers


def _parse_tasks(raw: dict) -> dict[str, TaskConfig]:
    tasks: dict[str, TaskConfig] = {}
    for name, cfg in (raw or {}).items():
        tasks[name] = TaskConfig(
            provider=cfg["provider"],
            model=cfg["model"],
        )
    # 默认回退：refine_text 用 video_analyze 的 provider。
    # （texts 和 scripts 审阅共用同一个 refine 任务，配置更简单）
    # 用户可以在 ai.tasks 里显式覆盖。
    if "refine_text" not in tasks and "video_analyze" in tasks:
        src = tasks["video_analyze"]
        tasks["refine_text"] = TaskConfig(provider=src.provider, model=src.model)
    return tasks


def _load_context(ai_raw: dict, base: Path) -> str:
    """加载 AI 上下文规范：可内联（ai.context），也可放文件（ai.context_file）。"""
    inline = (ai_raw.get("context") or "").strip()
    if inline:
        return inline
    file_ref = (ai_raw.get("context_file") or "").strip()
    if not file_ref:
        return ""
    path = _path(file_ref, base)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _legacy_ai_config(raw: dict) -> AIConfig:
    """兼容旧版 gemini: 配置块。"""
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


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    config_file = Path(config_path).resolve()
    base = config_file.parent
    _load_dotenv(base)

    with config_file.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    paths_raw = raw.get("paths", {})
    ai_raw = raw.get("ai")

    if ai_raw:
        ai = AIConfig(
            providers=_parse_providers(ai_raw.get("providers")),
            tasks=_parse_tasks(ai_raw.get("tasks")),
            context=_load_context(ai_raw, base),
        )
    else:
        ai = _legacy_ai_config(raw)

    return AppConfig(
        paths=PathsConfig(
            input_dir=_path(paths_raw.get("input_dir", "."), base),
            output_dir=_path(paths_raw.get("output_dir", "./output"), base),
            ffmpeg=paths_raw.get("ffmpeg", ""),
            ffprobe=paths_raw.get("ffprobe", ""),
            recursive=paths_raw.get("recursive", False),
            logs_dir=_path(paths_raw.get("logs_dir", "./logs"), base),
        ),
        proxy=ProxyConfig(**raw.get("proxy", {})),
        ai=ai,
        compress=CompressConfig(**raw.get("compress", {})),
        analyze=AnalyzeConfig(**raw.get("analyze", {})),
        naming=NamingConfig(**raw.get("naming", {})),
        script=ScriptConfig(
            scripts_subdir=raw.get("script", {}).get("scripts_subdir", "scripts"),
            template_file=_path(
                raw.get("script", {}).get("template_file", "./templates/vlog_template.md"),
                base,
            ),
            target_words=raw.get("script", {}).get("target_words", 80),
        ),
        plan=PlanConfig(**raw.get("plan", {})),
    )


def apply_run_paths(
    config: AppConfig,
    input_dir: Path | None = None,
    output_dir: Path | None = None,
    output_by_input_name: bool = True,
) -> AppConfig:
    """CLI 覆盖输入/输出目录。"""
    if input_dir:
        config.paths.input_dir = input_dir.resolve()
    if output_dir:
        config.paths.output_dir = output_dir.resolve()
    elif input_dir and output_by_input_name:
        config.paths.output_dir = (config.paths.output_dir / input_dir.name).resolve()
    return config
