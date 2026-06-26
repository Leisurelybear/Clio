from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vlog_tool.config.enums import WhisperDevice, WhisperLang, WhisperModelSize


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
    max_tokens: int = 4096


@dataclass
class TaskConfig:
    provider: str
    model: str


@dataclass
class AIConfig:
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    tasks: dict[str, TaskConfig] = field(default_factory=dict)
    context: str = ""
    debug_print_prompt: bool = False
    provider_ttl_min: int = 60


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
    reencode_split: bool = False


@dataclass
class AnalyzeConfig:
    compressed_subdir: str = "compressed"
    texts_subdir: str = "texts"
    skip_existing: bool = True
    max_analyze_duration_min: int = 30
    max_workers: int = 1


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


@dataclass
class WhisperConfig:
    enabled: bool = True
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
class ServerConfig:
    api_token: str | None = None


@dataclass
class AppConfig:
    paths: PathsConfig
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
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
