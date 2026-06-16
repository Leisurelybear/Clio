from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
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
    retry_attempts: int = 2
    requests_per_minute: int = 0


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
    split_max_min: int = 15
    splits_subdir: str = "splits"


@dataclass
class AnalyzeConfig:
    compressed_subdir: str = "compressed"
    texts_subdir: str = "texts"
    skip_existing: bool = True
    max_analyze_duration_min: int = 30


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
    use_transcripts: bool = True


class WhisperModelSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V3 = "large-v3"


class WhisperLang(StrEnum):
    ZH = "zh"
    EN = "en"
    AUTO = "auto"


class WhisperDevice(StrEnum):
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


@dataclass
class WhisperConfig:
    enabled: bool = False
    model_size: str = "medium"
    language: str = "zh"
    device: str = "auto"
    max_segments_per_clip: int = 5
    cache_dir: str | None = None
    transcripts_subdir: str = "transcripts"
    hf_endpoint: str = ""

    def sanitize(self) -> None:
        if self.model_size not in list(WhisperModelSize):
            raise ValueError(f"whisper.model_size 必须是 {', '.join(WhisperModelSize)}，当前: {self.model_size}")
        if self.language not in list(WhisperLang):
            raise ValueError(f"whisper.language 必须是 {', '.join(WhisperLang)}，当前: {self.language}")
        if self.device not in list(WhisperDevice):
            raise ValueError(f"whisper.device 必须是 {', '.join(WhisperDevice)}，当前: {self.device}")
        if self.max_segments_per_clip < 1:
            raise ValueError(f"plan.max_segments_per_clip 必须 >= 1，当前: {self.max_segments_per_clip}")


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
    whisper: WhisperConfig = field(default_factory=WhisperConfig)

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
            retry_attempts=cfg.get("retry_attempts", 2),
            requests_per_minute=cfg.get("requests_per_minute", 0),
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


def _load_context(ai_raw: dict, base: Path, project_dir: Path | None = None) -> str:
    """加载 AI 上下文规范。

    优先级：
    1. ai.context（内联文本）
    2. ai.context_file 在 project_dir 下（如果指定了 project_dir）
    3. ai.context_file 在 config.yaml 所在目录
    """
    inline = (ai_raw.get("context") or "").strip()
    if inline:
        return inline
    file_ref = (ai_raw.get("context_file") or "").strip()
    if not file_ref:
        return ""
    # 优先 project_dir（允许 project.yaml 覆盖后使用项目本地文件）
    if project_dir is not None:
        path = _path(file_ref, project_dir)
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    # 回退到 config.yaml 所在目录
    path = _path(file_ref, base)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


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


def _filter_dc(raw: dict, dc: type) -> dict:
    fields = {f.name for f in dc.__dataclass_fields__.values()}
    return {k: v for k, v in raw.items() if k in fields}


def _parse_whisper(raw: dict) -> WhisperConfig:
    cfg = WhisperConfig(**_filter_dc(raw, WhisperConfig))
    cfg.sanitize()
    return cfg


def _validate_config(config: AppConfig) -> None:
    """早期校验：让拼写错误和明显遗漏在 load 时就 fail，不要等到运行时。"""
    if config.proxy.enabled and not config.proxy.url:
        raise ValueError(
            "proxy.enabled=true 但 proxy.url 为空。请填写 url（如 socks5://127.0.0.1:1080），或把 enabled 改成 false。"
        )
    provider_names = set(config.ai.providers)
    for task_name, task_cfg in config.ai.tasks.items():
        if task_cfg.provider not in provider_names:
            available = ", ".join(sorted(provider_names)) or "<无>"
            raise ValueError(
                f"ai.tasks.{task_name}.provider = '{task_cfg.provider}'，"
                f"但 ai.providers 里没有这个名字。"
                f"已配置的厂家: {available}。"
                "请检查拼写，或在 ai.providers 里补上对应厂家。"
            )


def deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个 dict：override 中的值覆盖 base 的同名 key。

    对嵌套 dict 递归合并（不是替换），其它类型直接覆盖。
    返回新 dict，不修改入参。
    """
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


def load_config(
    config_path: str | Path = "config.yaml",
    project_dir: Path | None = None,
) -> AppConfig:
    config_file = Path(config_path).resolve()
    base = config_file.parent
    _load_dotenv(base)

    with config_file.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    # Deep-merge project.yaml 中的配置（如果存在）
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
    """CLI 覆盖输入/输出目录。返回新对象，不修改入参。"""
    config = deepcopy(config)
    if input_dir:
        config.paths.input_dir = input_dir.resolve()
    if output_dir:
        config.paths.output_dir = output_dir.resolve()
    elif input_dir and output_by_input_name:
        config.paths.output_dir = (config.paths.output_dir / input_dir.name).resolve()
    return config
