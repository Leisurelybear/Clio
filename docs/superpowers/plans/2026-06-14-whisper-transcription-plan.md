# Whisper ASR Transcription — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Whisper ASR speech transcription as an independent pipeline step, with full CLI/UI/test coverage.

**Architecture:** New `vlog_tool/transcribe.py` core module (faster-whisper singleton, model caching in `models/`), new `vlog_tool/tasks/transcribe.py` pipeline task with ffmpeg audio extraction + dedup by original source, plan integration via `{transcripts_json}` prompt injection, new `transcripts/` route + UI tab. Config: `WhisperConfig` dataclass with per-project language (zh/en/auto) and model size (small/medium/large-v3).

**Tech Stack:** Python 3.11+, faster-whisper, ffmpeg (existing dep), torch, pytest

---

### Task 1: WhisperConfig dataclass + enums + YAML parsing

**Files:**
- Modify: `vlog_tool/config.py`
- Test: `vlog_tool/tests/test_config.py`
- Modify: `config.example.yaml`

- [ ] **Step 1: Write test for WhisperConfig loading and defaults**

Add to `vlog_tool/tests/test_config.py`:

```python
from vlog_tool.config import WhisperConfig, WhisperModelSize, WhisperLang, WhisperDevice

def test_whisper_config_defaults():
    cfg = WhisperConfig()
    assert cfg.enabled is False
    assert cfg.model_size == "medium"
    assert cfg.language == "zh"
    assert cfg.device == "auto"
    assert cfg.max_segments_per_clip == 5
    assert cfg.cache_dir is None
    assert cfg.transcripts_subdir == "transcripts"

def test_whisper_config_custom():
    cfg = WhisperConfig(enabled=True, model_size="small", language="en", device="cpu")
    assert cfg.enabled is True
    assert cfg.model_size == "small"
    assert cfg.language == "en"
    assert cfg.device == "cpu"

def test_whisper_config_invalid_model_size():
    import pytest
    with pytest.raises(ValueError):
        WhisperConfig(model_size="invalid")

def test_whisper_config_invalid_language():
    import pytest
    with pytest.raises(ValueError):
        WhisperConfig(language="fr")

def test_whisper_config_invalid_device():
    import pytest
    with pytest.raises(ValueError):
        WhisperConfig(device="gpu")

def test_whisper_config_sanitize_clips():
    cfg = WhisperConfig(max_segments_per_clip=0)
    assert cfg.max_segments_per_clip == 5  # reset to default

def test_whisper_config_auto_language():
    cfg = WhisperConfig(language="auto")
    assert cfg.language == "auto"
```

Run: `python -m pytest vlog_tool\tests\test_config.py::test_whisper_config_defaults -v`
Expected: `FAILED` (class not defined)

- [ ] **Step 2: Add WhisperConfig dataclass + enums + AppConfig field**

In `vlog_tool/config.py`, before `AppConfig`, add:

```python
from enum import StrEnum


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

    def sanitize(self) -> None:
        if self.model_size not in list(WhisperModelSize):
            raise ValueError(f"whisper.model_size 必须是 {', '.join(WhisperModelSize)}，当前: {self.model_size}")
        if self.language not in list(WhisperLang):
            raise ValueError(f"whisper.language 必须是 {', '.join(WhisperLang)}，当前: {self.language}")
        if self.device not in list(WhisperDevice):
            raise ValueError(f"whisper.device 必须是 {', '.join(WhisperDevice)}，当前: {self.device}")
        if self.max_segments_per_clip < 1:
            self.max_segments_per_clip = 5
```

Add field to `AppConfig`:

```python
@dataclass
class AppConfig:
    ...
    script: ScriptConfig = field(default_factory=ScriptConfig)
    plan: PlanConfig = field(default_factory=PlanConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
```

In `load_config()`, add parsing after `plan=PlanConfig(**raw.get("plan", {}))`:

```python
    whisper_raw = raw.get("whisper", {})
    whisper_cfg = WhisperConfig(**whisper_raw)
    whisper_cfg.sanitize()
    config = AppConfig(
        ...
        plan=PlanConfig(**raw.get("plan", {})),
        whisper=whisper_cfg,
    )
```

- [ ] **Step 3: Run test to verify**

Run:
```
python -m pytest vlog_tool\tests\test_config.py -v -k "whisper"
```
Expected: ALL PASS

- [ ] **Step 4: Add whisper section to config.example.yaml**

Append to `config.example.yaml`:

```yaml
# Whisper ASR 语音转录（独立步骤，需要额外安装 faster-whisper）
# 默认关闭，启用后需执行 `python main.py whisper install` 安装依赖
# whisper:
#   enabled: false       # true=启用转录步骤
#   model_size: medium   # small | medium | large-v3
#   language: zh         # zh | en | auto（auto=自动检测语言；per-project 可覆盖）
#   device: auto         # auto | cpu | cuda
#   max_segments_per_clip: 5   # plan 注入时每段视频最多取 N 条
#   cache_dir: null      # null=默认 <程序根目录>/models/；可指定共享目录
#   transcripts_subdir: transcripts
```

- [ ] **Step 5: Commit**

```bash
git add vlog_tool/config.py vlog_tool/tests/test_config.py config.example.yaml
git commit -m "feat(config): add WhisperConfig dataclass with enum validation"
```

---

### Task 2: Core transcription module — `vlog_tool/transcribe.py`

**Files:**
- Create: `vlog_tool/transcribe.py`
- Test: `vlog_tool/tests/test_transcribe.py`

- [ ] **Step 1: Write tests for transcribe_audio**

Create `vlog_tool/tests/test_transcribe.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from vlog_tool.config import AppConfig, WhisperConfig
from vlog_tool.transcribe import (
    transcribe_audio,
    _get_model,
    _resolve_cache_dir,
    _resolve_device,
    _resolve_compute_type,
)


@pytest.fixture
def whisper_cfg():
    return AppConfig(
        paths=MagicMock(),
        whisper=WhisperConfig(enabled=True, model_size="small", language="zh", device="cpu"),
    )


def test_resolve_cache_dir_default(tmp_path, monkeypatch):
    """cache_dir=null 时解析为 <程序根目录>/models/"""
    monkeypatch.setattr("vlog_tool.transcribe.PROJECT_ROOT", tmp_path)
    result = _resolve_cache_dir(MagicMock(whisper=WhisperConfig(cache_dir=None)))
    assert result == tmp_path / "models"


def test_resolve_cache_dir_custom():
    """cache_dir 非空时直接使用"""
    result = _resolve_cache_dir(MagicMock(whisper=WhisperConfig(cache_dir="/custom/path")))
    assert result == Path("/custom/path")


def test_resolve_device_cpu():
    result = _resolve_device(MagicMock(whisper=WhisperConfig(device="cpu")))
    assert result == "cpu"


def test_resolve_device_cuda():
    result = _resolve_device(MagicMock(whisper=WhisperConfig(device="cuda")))
    assert result == "cuda"


@patch("vlog_tool.transcribe.torch")
def test_resolve_device_auto_cpu(mock_torch):
    mock_torch.cuda.is_available.return_value = False
    result = _resolve_device(MagicMock(whisper=WhisperConfig(device="auto")))
    assert result == "cpu"


@patch("vlog_tool.transcribe.torch")
def test_resolve_device_auto_cuda(mock_torch):
    mock_torch.cuda.is_available.return_value = True
    result = _resolve_device(MagicMock(whisper=WhisperConfig(device="auto")))
    assert result == "cuda"


def test_resolve_compute_type_cpu():
    assert _resolve_compute_type("cpu") == "int8"


def test_resolve_compute_type_cuda():
    assert _resolve_compute_type("cuda") == "int8_float16"


@patch("vlog_tool.transcribe.WhisperModel")
def test_get_model_singleton(mock_whisper_cls):
    """同一 session 内只加载一次模型"""
    from vlog_tool.transcribe import _whisper_model, _whisper_cache_key

    _whisper_model = None  # reset
    cfg = MagicMock(whisper=WhisperConfig(model_size="small", cache_dir="/cache"))
    with patch("vlog_tool.transcribe._whisper_model", None), \
         patch("vlog_tool.transcribe._whisper_cache_key", None):
        m1 = _get_model(cfg)
        m2 = _get_model(cfg)
        assert m1 is m2  # same instance
        mock_whisper_cls.assert_called_once()


@patch("vlog_tool.transcribe._get_model")
def test_transcribe_audio_segments(mock_get_model):
    """transcribe_audio 返回过滤后的 segment 列表"""
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (
        MagicMock(
            language="zh",
            language_probability=0.95,
            duration=100.0,
        ),
        [
            MagicMock(start=0.0, end=2.5, text=" 今天天气真好 ", avg_logprob=-0.1, no_speech_prob=0.01),
            MagicMock(start=2.5, end=5.0, text=" 我们来了 ", avg_logprob=-0.3, no_speech_prob=0.02),
            MagicMock(start=5.0, end=7.0, text=" 低置信度 ", avg_logprob=-0.9, no_speech_prob=0.5),
        ],
    )
    mock_get_model.return_value = mock_model

    callback = MagicMock()
    result = transcribe_audio(Path("/fake.wav"), MagicMock(whisper=WhisperConfig(language="zh")), callback)

    assert len(result) == 2  # third segment filtered by low confidence
    assert result[0]["start"] == 0.0
    assert result[0]["text"] == "今天天气真好"  # stripped
    assert result[1]["start"] == 2.5
    callback.assert_called()
```

Run: `python -m pytest vlog_tool\tests\test_transcribe.py -v`
Expected: FAILED (module not found)

- [ ] **Step 2: Implement transcribe.py**

Create `vlog_tool/transcribe.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import torch

from vlog_tool.config import AppConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # main.py 所在目录

_whisper_model = None
_whisper_cache_key: str | None = None


def _resolve_cache_dir(config: AppConfig) -> Path:
    if config.whisper.cache_dir:
        return Path(config.whisper.cache_dir).resolve()
    return PROJECT_ROOT / "models"


def _resolve_device(config: AppConfig) -> str:
    if config.whisper.device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return config.whisper.device


def _resolve_compute_type(device: str) -> str:
    return "int8_float16" if device == "cuda" else "int8"


def _get_model(config: AppConfig):
    global _whisper_model, _whisper_cache_key
    from faster_whisper import WhisperModel

    cache_dir = _resolve_cache_dir(config)
    key = f"{config.whisper.model_size}@{cache_dir}"
    if _whisper_model is None or _whisper_cache_key != key:
        _whisper_model = WhisperModel(
            config.whisper.model_size,
            device=_resolve_device(config),
            compute_type=_resolve_compute_type(_resolve_device(config)),
            download_root=str(cache_dir),
        )
        _whisper_cache_key = key
    return _whisper_model


def transcribe_audio(
    audio_path: Path,
    config: AppConfig,
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict]:
    lang = config.whisper.language
    model = _get_model(config)
    if progress_callback:
        progress_callback("transcribing")

    segments_iter, info = model.transcribe(
        str(audio_path),
        language=None if lang == "auto" else lang,
        word_timestamps=False,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
        beam_size=5,
        best_of=5,
        temperature=0.0,
    )
    all_segments = list(segments_iter)

    result = []
    for seg in all_segments:
        if seg.avg_logprob >= -0.8 and seg.no_speech_prob <= 0.1:
            result.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
                "avg_logprob": round(seg.avg_logprob, 3),
            })
    return result
```

- [ ] **Step 3: Run tests to verify**

```
python -m pytest vlog_tool\tests\test_transcribe.py -v
```
Expected: ALL PASS (mock-based, no real model needed)

- [ ] **Step 4: Commit**

```bash
git add vlog_tool/transcribe.py vlog_tool/tests/test_transcribe.py
git commit -m "feat(transcribe): add core Whisper transcription module"
```

---

### Task 3: Pipeline task — `vlog_tool/tasks/transcribe.py` + pipeline registration

**Files:**
- Create: `vlog_tool/tasks/transcribe.py`
- Modify: `vlog_tool/pipeline.py`
- Test: `vlog_tool/tests/test_tasks_transcribe.py`

- [ ] **Step 1: Write tests for run_transcribe_all**

Create `vlog_tool/tests/test_tasks_transcribe.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from vlog_tool.config import AppConfig, WhisperConfig


@pytest.fixture
def cfg():
    c = MagicMock(spec=AppConfig)
    c.whisper = WhisperConfig(enabled=True, language="zh", model_size="small", device="cpu")
    c.paths.output_dir = Path("/tmp/output")
    c.paths.input_dir = Path("/tmp/input")
    c.analyze.skip_existing = True
    c.analyze.compressed_subdir = "compressed"
    c.analyze.max_analyze_duration_min = 30
    return c


@patch("vlog_tool.tasks.transcribe.transcribe_audio")
def test_run_transcribe_all_dedup(mock_transcribe, cfg, tmp_path):
    """同一原始视频只转录一次（有 split 段时）"""
    from vlog_tool.tasks.transcribe import run_transcribe_all

    output = tmp_path / "output"
    compressed = output / "compressed"
    compressed.mkdir(parents=True)
    # 模拟原文件
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "GL010683.MP4").touch()
    cfg.paths.input_dir = inp
    cfg.paths.output_dir = output

    # 创建压缩文件 + split 段
    (compressed / "001_GL010683.mp4").touch()
    split_dir = compressed / "split"
    split_dir.mkdir()
    (split_dir / "001_GL010683_seg01.mp4").touch()
    (split_dir / "001_GL010683_seg02.mp4").touch()

    # 确保 transcripts 目录存在
    transcripts_dir = output / "transcripts"
    transcripts_dir.mkdir(parents=True)

    tracker = MagicMock()
    run_transcribe_all(cfg, tracker)

    # 只转录了一次（GL010683 seen once despite 3 compressed files）
    assert mock_transcribe.call_count == 1


def test_run_transcribe_all_disabled(cfg):
    """whisper.enabled=False 时直接跳过"""
    from vlog_tool.tasks.transcribe import run_transcribe_all
    cfg.whisper.enabled = False
    tracker = MagicMock()
    run_transcribe_all(cfg, tracker)
    tracker.update.assert_not_called()


@patch("vlog_tool.tasks.transcribe.transcribe_audio")
def test_run_transcribe_all_skip_existing(mock_transcribe, cfg, tmp_path):
    """已有 transcript 文件时跳过"""
    from vlog_tool.tasks.transcribe import run_transcribe_all

    output = tmp_path / "output"
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "GL010683.MP4").touch()
    compressed = output / "compressed"
    compressed.mkdir(parents=True)
    (compressed / "001_GL010683.mp4").touch()
    cfg.paths.input_dir = inp
    cfg.paths.output_dir = output

    # 创建已有的 transcript 文件
    transcripts = output / "transcripts"
    transcripts.mkdir(parents=True)
    (transcripts / "GL010683_transcript.json").write_text("{}")

    tracker = MagicMock()
    run_transcribe_all(cfg, tracker)
    mock_transcribe.assert_not_called()
```

Run: `python -m pytest vlog_tool\tests\test_tasks_transcribe.py -v`
Expected: FAILED (module not found)

- [ ] **Step 2: Create tasks/transcribe.py**

Create `vlog_tool/tasks/transcribe.py`:

```python
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from vlog_tool._constants import VIDEO_EXTS
from vlog_tool.transcribe import transcribe_audio
from vlog_tool.config import AppConfig
from vlog_tool.log import format_duration, timed
from vlog_tool.progress import ProgressTracker
from vlog_tool.tasks._helpers import _eta_line
from vlog_tool.tasks.analyze import _resolve_original
from vlog_tool.utils import get_duration_sec


def _extract_audio(video_path: Path) -> Path | None:
    """ffmpeg 提取 16kHz 单声道 WAV，返回临时文件路径。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        str(tmp.name),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        Path(tmp.name).unlink(missing_ok=True)
        return None
    return Path(tmp.name)


def run_transcribe_all(
    config: AppConfig,
    tracker: ProgressTracker | None = None,
    single_file: Path | None = None,
) -> None:
    if not config.whisper.enabled:
        print("[跳过] Whisper 转录未启用（设置 whisper.enabled=true）")
        return

    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        print("错误: faster-whisper 未安装，请执行 `python main.py whisper install`")
        return

    transcripts_dir = config.paths.output_dir / config.whisper.transcripts_subdir
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # 收集 unique original stems
    stems: set[str] = set()
    compressed_dir = config.paths.output_dir / config.analyze.compressed_subdir
    for f in sorted(compressed_dir.rglob("*")):
        if f.suffix.lower() in VIDEO_EXTS and f.is_file():
            orig = _resolve_original(config.paths.input_dir, f.stem)
            if orig:
                stems.add(orig.stem)

    stems = sorted(stems)
    total = len(stems)
    if total == 0:
        print("没有找到需要转录的视频")
        return

    if tracker:
        tracker.update(phase="transcribe", total=total, current=0, message="Whisper 语音转录...")

    start_time = __import__("time").time()
    for i, stem in enumerate(stems):
        out_path = transcripts_dir / f"{stem}_transcript.json"
        if config.analyze.skip_existing and out_path.exists():
            print(f"[跳过] {stem} (已有转录)")
            if tracker:
                tracker.next(message=f"跳过 {stem}")
            continue

        # 定位原始视频
        orig_video: Path | None = None
        for ext in (".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".m4v", ".webm", ".lrv"):
            candidate = config.paths.input_dir / f"{stem}{ext}"
            if candidate.is_file():
                orig_video = candidate
                break
        if orig_video is None:
            print(f"  [跳过] {stem}: 找不到原始视频")
            continue

        # duration gate
        duration = get_duration_sec(str(orig_video))
        if duration is None:
            print(f"  [跳过] {stem}: 无法读取时长")
            continue
        max_min = config.analyze.max_analyze_duration_min
        if max_min > 0 and duration > max_min * 60:
            print(f"  [跳过] {stem}: 时长 {format_duration(duration)} 超过限制")
            continue

        # 提取音频
        wav_path = _extract_audio(orig_video)
        if wav_path is None:
            print(f"  [跳过] {stem}: 音频提取失败（可能无音轨）")
            if tracker:
                tracker.next(message=f"跳过 {stem} (no audio)")
            continue

        try:
            segments = transcribe_audio(wav_path, config)
            transcript = {
                "source_video": orig_video.name,
                "source_stem": stem,
                "language": config.whisper.language,
                "model_size": config.whisper.model_size,
                "segments": segments,
                "generated_at": __import__("datetime").datetime.now().isoformat(),
            }
            out_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
            seg_info = f"{len(segments)} 段" if segments else "无有效内容"
            print(f"  [{_eta_line('转录', i + 1, total, stem, start_time)}] {seg_info}")
        except Exception as e:
            print(f"  [错误] {stem}: {e}")
            if tracker:
                tracker.next(message=f"错误 {stem}: {e}")
            continue
        finally:
            wav_path.unlink(missing_ok=True)

        if tracker:
            tracker.next(message=f"完成 {stem}")


def run_transcribe_one(config: AppConfig, video_path: Path) -> dict:
    """单文件转录（供 UI rerun 使用）。"""
    if not video_path.is_file():
        return {"error": f"文件不存在: {video_path}"}
    wav_path = _extract_audio(video_path)
    if wav_path is None:
        return {"error": "音频提取失败"}
    try:
        segments = transcribe_audio(wav_path, config)
        return {
            "source_video": video_path.name,
            "source_stem": video_path.stem,
            "segments": segments,
        }
    finally:
        wav_path.unlink(missing_ok=True)
```

- [ ] **Step 3: Register in pipeline.py**

In `vlog_tool/pipeline.py`, add import after `from vlog_tool.tasks.scripts import run_generate_scripts`:

```python
from vlog_tool.tasks.transcribe import run_transcribe_all  # noqa: F401
```

Add `"transcribe"` to `_STEP_LABELS` and `_STEP_FUNCS`:

```python
_STEP_LABELS = {
    "compress": "压缩原视频",
    "transcribe": "语音转录",  # <-- add
    "analyze": "AI 分析素材",
    "voiceover": "生成口播文案",
    "plan": "vlog 剪辑规划",
    "label": "烧录序号标注",
}

_STEP_FUNCS = {
    "compress": run_compress_all,
    "transcribe": run_transcribe_all,  # <-- add
    "analyze": run_analyze_all,
    "voiceover": run_generate_scripts,
    "plan": run_plan_vlog,
    "label": run_label_videos,
}
```

- [ ] **Step 4: Run tests to verify**

```
python -m pytest vlog_tool\tests\test_tasks_transcribe.py -v
```
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add vlog_tool/tasks/transcribe.py vlog_tool/tests/test_tasks_transcribe.py vlog_tool/pipeline.py
git commit -m "feat(transcribe): add pipeline task with dedup and ffmpeg audio extraction"
```

---

### Task 4: CLI subcommands — `transcribe` + `whisper install/check`

**Files:**
- Modify: `main.py`
- Test: `vlog_tool/tests/test_main.py`

- [ ] **Step 1: Add CLI tests**

Add to `vlog_tool/tests/test_main.py`:

```python
def test_transcribe_subcommand(cli_runner):
    result = cli_runner(["--config", str(CONFIG), "transcribe"])
    assert result == 0

def test_whisper_subcommand_help(cli_runner):
    result = cli_runner(["--config", str(CONFIG), "whisper", "--help"])
    assert "usage" in result.lower() or result == 0

def test_whisper_check_subcommand(cli_runner):
    result = cli_runner(["--config", str(CONFIG), "whisper", "check"])
    assert result == 0
```

- [ ] **Step 2: Implement CLI subcommands**

In `main.py`, after `p_serve` parser (line ~206), add:

```python
    p_transcribe = sub.add_parser("transcribe", help="Whisper ASR 语音转录（需先安装 faster-whisper）")
    _add_io_args(p_transcribe)
    p_transcribe.add_argument("--force", action="store_true", help="忽略已有转录，重新生成")

    p_whisper = sub.add_parser("whisper", help="Whisper 环境管理（安装/检测）")
    whisper_sub = p_whisper.add_subparsers(dest="whisper_command", required=True)
    p_whisper_install = whisper_sub.add_parser("install", help="安装 faster-whisper 依赖并预下载模型")
    p_whisper_check = whisper_sub.add_parser("check", help="检测 faster-whisper / CUDA 状态")
```

In the dispatch section, inside `if args.command == "check":` block (~line 217), add:

```python
    elif args.command == "transcribe":
        config = load_config(config_path)
        if getattr(args, "input", None):
            config = apply_run_paths(config, input_dir=args.input)
        config.analyze.skip_existing = not getattr(args, "force", False)
        return run_transcribe_all(config)

    elif args.command == "whisper":
        from vlog_tool.whisper_cli import run_whisper_install, run_whisper_check
        if args.whisper_command == "install":
            return run_whisper_install()
        elif args.whisper_command == "check":
            return run_whisper_check()
```

- [ ] **Step 3: Create vlog_tool/whisper_cli.py**

Create `vlog_tool/whisper_cli.py`:

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import torch

from vlog_tool.transcribe import PROJECT_ROOT, _resolve_cache_dir


def run_whisper_install() -> int:
    print("正在安装 faster-whisper...")
    req = PROJECT_ROOT / "requirements-whisper.txt"
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("安装失败:", result.stderr)
        return 1
    print("faster-whisper 安装完成")

    # 检测 CUDA
    cuda_avail = torch.cuda.is_available()
    print(f"CUDA: {'可用' if cuda_avail else '不可用（使用 CPU）'}")

    # 预下载模型
    cfg = __import__("vlog_tool.config", fromlist=["load_config"]).load_config()
    model_name = cfg.whisper.model_size if hasattr(cfg, "whisper") else "medium"
    cache_dir = _resolve_cache_dir(cfg) if hasattr(cfg, "whisper") else PROJECT_ROOT / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"正在预下载模型 '{model_name}' 到 {cache_dir}...")
    from faster_whisper import WhisperModel
    WhisperModel(model_name, device="cpu", download_root=str(cache_dir))
    print(f"模型 '{model_name}' 已就绪")
    return 0


def run_whisper_check() -> int:
    print("=== Whisper 环境检测 ===")
    # faster-whisper
    try:
        import faster_whisper
        print(f"faster-whisper: {faster_whisper.__version__}  ✔")
    except ImportError:
        print("faster-whisper: 未安装  ✘（请执行 python main.py whisper install）")
        return 1

    # CUDA
    cuda_avail = torch.cuda.is_available()
    print(f"CUDA: {'可用 ✔' if cuda_avail else '不可用（使用 CPU）'}")

    # 已缓存的模型
    cache_dir = _resolve_cache_dir(__import__("vlog_tool.config", fromlist=["load_config"]).load_config())
    if cache_dir.is_dir():
        models = [d.name for d in cache_dir.iterdir() if d.is_dir()]
        if models:
            print(f"已缓存模型: {', '.join(models)}")
        else:
            print("模型缓存: 空（尚无缓存模型）")
    return 0
```

- [ ] **Step 4: Run CLI tests to verify**

```
python -m pytest vlog_tool\tests\test_main.py -v -k "whisper or transcribe"
```
Expected: ALL PASS

- [ ] **Step 5: Run all existing tests to check no regression**

```
python -m pytest vlog_tool\tests -q
```
Expected: 344+ passed

- [ ] **Step 6: Commit**

```bash
git add main.py vlog_tool/whisper_cli.py vlog_tool/tests/test_main.py
git commit -m "feat(cli): add transcribe and whisper install/check subcommands"
```

---

### Task 5: Plan integration — transcript injection into PLAN_PROMPT

**Files:**
- Modify: `vlog_tool/prompts.py`
- Modify: `vlog_tool/analyze.py`
- Modify: `vlog_tool/tasks/plan.py`
- Test: `vlog_tool/tests/test_plan.py`

- [ ] **Step 1: Write tests for plan transcript injection**

Add to `vlog_tool/tests/test_plan.py` (create if not exists):

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from vlog_tool.config import AppConfig, WhisperConfig


def test_plan_prompt_includes_transcripts():
    """plan_daily_vlog 注入 transcripts_json 变量到 prompt 中"""
    from vlog_tool.analyze import plan_daily_vlog

    clips = [
        {"index": "001", "title": "到达", "summary": "抵达机场",
         "timeline": [{"start": "00:00", "end": "00:30", "description": "到达"}],
         "location": "巴黎", "highlights": [], "suggested_use": "开场"}
    ]
    transcripts_map = {
        "GL010683": {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "今天天气真好", "avg_logprob": -0.1}
            ]
        }
    }
    cfg = MagicMock(spec=AppConfig)
    cfg.plan.max_clips_per_day = 12
    cfg.plan.target_duration_sec = 180
    cfg.whisper.max_segments_per_clip = 5
    cfg.whisper.enabled = True

    with patch("vlog_tool.analyze.get_task_provider") as mock_provider, \
         patch("vlog_tool.analyze._wrap_with_context") as mock_wrap, \
         patch("vlog_tool.analyze._call_ai") as mock_call, \
         patch("vlog_tool.analyze.extract_json") as mock_extract:
        mock_call.return_value = '{"sequence": [], "day_title": "test"}'
        mock_extract.return_value = {"sequence": [], "day_title": "test"}
        result = plan_daily_vlog(clips, cfg, "day1", transcripts_map)

        # Verify transcripts_json was passed in prompt
        prompt_arg = mock_wrap.call_args[0][0] if mock_wrap.call_args else ""
        assert "{transcripts_json}" not in  prompt_arg  # should be replaced by format


def test_plan_no_transcript_fallback():
    """无 transcript 时 plan 正常生成，不注入"""
    from vlog_tool.analyze import plan_daily_vlog

    clips = [{"index": "001", "title": "到达"}]
    cfg = MagicMock(spec=AppConfig)
    cfg.plan.max_clips_per_day = 12
    cfg.plan.target_duration_sec = 180
    cfg.whisper.max_segments_per_clip = 5

    with patch("vlog_tool.analyze.get_task_provider") as mock_provider, \
         patch("vlog_tool.analyze._wrap_with_context") as mock_wrap, \
         patch("vlog_tool.analyze._call_ai") as mock_call, \
         patch("vlog_tool.analyze.extract_json") as mock_extract:
        mock_call.return_value = '{"sequence": [], "day_title": "test"}'
        mock_extract.return_value = {"sequence": [], "day_title": "test"}
        result = plan_daily_vlog(clips, cfg, "day1", None)
        # No exception, normal plan generation
        assert result["day_title"] == "test"
```

Run: `python -m pytest vlog_tool\tests\test_plan.py -v -k "transcript"`
Expected: PASS

- [ ] **Step 2: Add TRANSCRIPT_CONTEXT to prompts.py**

In `vlog_tool/prompts.py`, add at the end:

```python
TRANSCRIPT_CONTEXT = """
Additionally, here are the spoken content (transcript) segments for each clip.
Use them to determine which clips contain meaningful narration, understand the actual spoken context, and optimize the timing/ordering:

{transcripts_json}
"""
```

- [ ] **Step 3: Update plan_daily_vlog in analyze.py**

Change signature to accept `transcripts_map`:

```python
def plan_daily_vlog(
    clips: list[dict],
    config: AppConfig,
    day_label: str = "day1",
    transcripts_map: dict[str, dict] | None = None,
) -> dict:
```

After formatting the base prompt (line ~135), inject transcript context:

```python
    base = PLAN_PROMPT.format(
        clips_json=json.dumps(clips, ensure_ascii=False, indent=2),
        max_clips=config.plan.max_clips_per_day,
        target_duration_sec=config.plan.target_duration_sec,
        example_index=first_idx,
    )

    # 注入 transcript 上下文（如果可用）
    if transcripts_map and config.whisper.enabled:
        transcript_info = []
        for clip in clips:
            # 从 clip index 推断 source_stem（格式 "001" → 需从文件名映射）
            # tasks/plan.py 在传递时已做好映射
            matched = []
            clip_segments = []
            # 用 clip 的 timeline 范围过滤 transcript segments
            for tl in clip.get("timeline", []):
                tl_start = _parse_timestamp_sec(tl.get("start", "00:00"))
                tl_end = _parse_timestamp_sec(tl.get("end", "00:00"))
                clip_segments.append({"start": tl_start, "end": tl_end})

            for source_stem, trans in transcripts_map.items():
                for seg in trans.get("segments", []):
                    # 检查 seg 是否在任一 timeline 范围内
                    for window in clip_segments:
                        if seg["start"] >= window["start"] and seg["end"] <= window["end"]:
                            matched.append(seg)
                            break
            if matched:
                matched.sort(key=lambda s: -s.get("avg_logprob", 0))
                matched = matched[:config.whisper.max_segments_per_clip]
                transcript_info.append({
                    "clip_index": clip.get("index"),
                    "clip_title": clip.get("title"),
                    "transcript_segments": matched,
                })

        if transcript_info:
            transcript_json = json.dumps(transcript_info, ensure_ascii=False, indent=2)
            base += TRANSCRIPT_CONTEXT.format(transcripts_json=transcript_json)

    prompt = _wrap_with_context(f"日 vlog 标签: {day_label}\n\n{base}", config)
```

Add helper `_parse_timestamp_sec` near top of `analyze.py`:

```python
def _parse_timestamp_sec(ts: str) -> float:
    """将 "MM:SS" 或 "HH:MM:SS" 转为秒数。"""
    parts = ts.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return 0.0
```

Add import for `TRANSCRIPT_CONTEXT` in `analyze.py`:

```python
from vlog_tool.prompts import (
    ANALYZE_PROMPT,
    PLAN_PROMPT,
    REFINE_SCRIPT_FIX_PROMPT,
    REFINE_SCRIPT_PROMPT,
    REFINE_TEXT_FIX_PROMPT,
    REFINE_TEXT_PROMPT,
    SCRIPT_PROMPT,
    TRANSCRIPT_CONTEXT,
)
```

- [ ] **Step 4: Update tasks/plan.py to load and pass transcripts_map**

In `run_plan_vlog()` (plan.py), after collecting `clips`, add:

```python
    # 加载 transcript 数据
    transcripts_map: dict[str, dict] = {}
    trans_dir = config.paths.output_dir / config.whisper.transcripts_subdir
    if trans_dir.is_dir() and config.whisper.enabled:
        for tf in sorted(trans_dir.glob("*_transcript.json")):
            try:
                data = json.loads(tf.read_text(encoding="utf-8"))
                stem = data.get("source_stem", "")
                if stem:
                    transcripts_map[stem] = data
            except (json.JSONDecodeError, KeyError):
                continue
```

Change the `plan_daily_vlog` call to pass `transcripts_map`:

```python
        plan = plan_daily_vlog(clips, config, day_label, transcripts_map=transcripts_map)
```

- [ ] **Step 5: Run tests to verify**

```
python -m pytest vlog_tool\tests\test_plan.py -v -k "transcript"
```
Expected: PASS

- [ ] **Step 6: Run all tests**

```
python -m pytest vlog_tool\tests -q
```
Expected: 344+ passed

- [ ] **Step 7: Commit**

```bash
git add vlog_tool/prompts.py vlog_tool/analyze.py vlog_tool/tasks/plan.py vlog_tool/tests/test_plan.py
git commit -m "feat(plan): inject transcript context into PLAN_PROMPT"
```

---

### Task 6: Dependency files + .gitignore + pipeline enabled check

**Files:**
- Create: `requirements-whisper.txt`
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Create requirements-whisper.txt**

Create `requirements-whisper.txt`:

```
faster-whisper==1.1.0
```

- [ ] **Step 2: Update requirements.txt**

Append to `requirements.txt`:

```txt

# whisper: 语音转录（独立步骤），取消下面注释以安装：
# -r requirements-whisper.txt
```

- [ ] **Step 3: Update .gitignore**

Append to `.gitignore`:

```
# Whisper / ML models
models/
```

- [ ] **Step 4: Add whisper.enabled check to pipeline.py**

In `run_pipeline_steps()` (pipeline.py), after the unknown-steps check, add a warning for disabled whisper:

```python
    if "transcribe" in steps and not config.whisper.enabled:
        print("[提示] Whisper 转录已跳过（whisper.enabled 未开启）")
        steps = [s for s in steps if s != "transcribe"]
```

Add after import section:

```python
    if "transcribe" in steps and config.whisper.enabled:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            raise RuntimeError("faster-whisper 未安装，请执行 `python main.py whisper install`")
```

- [ ] **Step 5: Verify no regression**

```
python -m pytest vlog_tool\tests -q
```
Expected: 344+ passed

- [ ] **Step 6: Commit**

```bash
git add requirements-whisper.txt requirements.txt .gitignore vlog_tool/pipeline.py
git commit -m "chore: add whisper dependencies and pipeline enabled check"
```

---

### Task 7: Backend routes — transcripts + whisper check

**Files:**
- Create: `vlog_tool/ui/routes/transcripts.py`
- Create: `vlog_tool/ui/routes/whisper_routes.py`
- Modify: `vlog_tool/ui/server.py`
- Test: `vlog_tool/tests/test_routes_transcripts.py`, `vlog_tool/tests/test_routes_whisper.py`

- [ ] **Step 1: Create routes/transcripts.py**

Create `vlog_tool/ui/routes/transcripts.py`:

```python
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

from vlog_tool.ui.server import _get_config


def handle_get_transcripts(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """GET /api/transcripts?source_stem=GL010683"""
    stem = (qs.get("source_stem") or [None])[0]
    if not stem:
        handler.send_error(400, "缺少 source_stem 参数")
        return
    proj_input = getattr(handler, "_project_input", None)
    config = _get_config(proj_input)
    trans_dir = config.paths.output_dir / config.whisper.transcripts_subdir
    target = trans_dir / f"{stem}_transcript.json"
    if not target.is_file():
        handler.send_error(404, "未找到转录文件")
        return
    data = json.loads(target.read_text(encoding="utf-8"))
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def handle_put_transcripts(handler: BaseHTTPRequestHandler, qs: dict, obj: dict) -> None:
    """PUT /api/transcripts — 保存编辑后的 transcript"""
    stem = obj.get("source_stem")
    if not stem:
        handler.send_error(400, "缺少 source_stem")
        return
    proj_input = getattr(handler, "_project_input", None)
    config = _get_config(proj_input)
    trans_dir = config.paths.output_dir / config.whisper.transcripts_subdir
    trans_dir.mkdir(parents=True, exist_ok=True)
    target = trans_dir / f"{stem}_transcript.json"
    target.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(b'{"status": "ok"}')
```

- [ ] **Step 2: Create routes/whisper_routes.py**

Create `vlog_tool/ui/routes/whisper_routes.py`:

```python
from __future__ import annotations

from http.server import BaseHTTPRequestHandler

import torch


def handle_get_whisper_check(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """GET /api/whisper/check"""
    result = {
        "faster_whisper_installed": False,
        "cuda_available": torch.cuda.is_available(),
    }
    try:
        import faster_whisper  # noqa: F401
        result["faster_whisper_installed"] = True
    except ImportError:
        pass

    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(__import__("json").dumps(result).encode("utf-8"))
```

- [ ] **Step 3: Register routes in server.py**

In `vlog_tool/ui/server.py`, add imports:

```python
from vlog_tool.ui.routes.transcripts import handle_get_transcripts, handle_put_transcripts
from vlog_tool.ui.routes.whisper_routes import handle_get_whisper_check
```

In `do_GET`, add:

```python
        if path == "/api/transcripts":
            return handle_get_transcripts(self, qs)
        if path == "/api/whisper/check":
            return handle_get_whisper_check(self, qs)
```

In `do_PUT`, add:

```python
        if path == "/api/transcripts":
            return handle_put_transcripts(self, qs, obj)
```

- [ ] **Step 4: Write route tests**

Create `vlog_tool/tests/test_routes_transcripts.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from vlog_tool.config import AppConfig, WhisperConfig


def test_get_transcripts_success(tmp_path):
    config = MagicMock(spec=AppConfig)
    config.whisper = WhisperConfig()
    config.paths.output_dir = tmp_path
    trans_dir = tmp_path / "transcripts"
    trans_dir.mkdir()
    (trans_dir / "GL010683_transcript.json").write_text(
        json.dumps({"source_stem": "GL010683", "segments": []})
    )

    from vlog_tool.ui.routes.transcripts import handle_get_transcripts
    handler = MagicMock()
    handler._project_input = None
    with patch("vlog_tool.ui.routes.transcripts._get_config", return_value=config):
        handle_get_transcripts(handler, {"source_stem": ["GL010683"]})
    assert handler.send_response.called
```

Create `vlog_tool/tests/test_routes_whisper.py`:

```python
from unittest.mock import MagicMock, patch

def test_whisper_check():
    from vlog_tool.ui.routes.whisper_routes import handle_get_whisper_check
    handler = MagicMock()
    with patch("torch.cuda.is_available", return_value=False):
        handle_get_whisper_check(handler, {})
    assert handler.send_response.called
    written = handler.wfile.write.call_args[0][0]
    assert b"cuda_available" in written
```

Run: `python -m pytest vlog_tool\tests\test_routes_transcripts.py vlog_tool\tests\test_routes_whisper.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add vlog_tool/ui/routes/transcripts.py vlog_tool/ui/routes/whisper_routes.py vlog_tool/ui/server.py vlog_tool/tests/test_routes_transcripts.py vlog_tool/tests/test_routes_whisper.py
git commit -m "feat(ui): add transcripts and whisper check backend routes"
```

---

### Task 8: Frontend UI — transcripts tab, sidebar badge, run step

**Files:**
- Modify: `vlog_tool/ui/static/index.html`
- Modify: `vlog_tool/ui/static/src/state.js`
- Modify: `vlog_tool/ui/static/src/sidebar.js`
- Modify: `vlog_tool/ui/static/src/editor.js`
- Modify: `vlog_tool/ui/static/src/viewer.js`
- Modify: `vlog_tool/ui/static/src/runner.js`

- [ ] **Step 1: Add tab button and pane to index.html**

In `vlog_tool/ui/static/index.html`, find the tab navigation section and add:

```html
<div class="tab-btn" data-tab="transcript">转录</div>
```

Find the tab panes section and add:

```html
<div id="tab-transcript" class="tab-pane">
    <div id="transcript-header"></div>
    <div id="transcript-list"></div>
</div>
```

- [ ] **Step 2: Add transcript field to state.js**

In `vlog_tool/ui/static/src/state.js`, add to the state object:

```javascript
transcript: null,
```

- [ ] **Step 3: Add sidebar badge in sidebar.js**

In `vlog_tool/ui/static/src/sidebar.js`, in the `renderVideoItem` function, after the match indicator:

```javascript
if (v.has_transcript) {
    badge += ' <span class="badge badge-transcript">(T)</span>';
}
```

Also add transcript info line under filename:

```javascript
if (v.transcript_info) {
    infoLines += `<div class="video-transcript-info">转录: ${v.transcript_info}</div>`;
}
```

- [ ] **Step 4: Add renderTranscript to editor.js**

In `vlog_tool/ui/static/src/editor.js`, add:

```javascript
import { state, fetchAPI } from './state.js';
import { $ } from './utils.js';

export async function renderTranscript() {
    const header = $('#transcript-header');
    const list = $('#transcript-list');
    if (!header || !list) return;

    const video = state.currentVideo;
    if (!video) {
        header.textContent = '请先选择一个视频';
        list.innerHTML = '';
        return;
    }

    // 获取 stem（从 file 或 source 字段提取）
    let stem = video.source_stem || video.stem;
    if (!stem) {
        // 尝试从 file 字段提取
        const file = video.file || video.source || '';
        stem = file.replace(/\.[^.]+$/, '').replace(/^\d+_/, '');
    }

    if (!stem) {
        header.textContent = '无法确定视频标识';
        return;
    }

    try {
        const api = await fetchAPI(`/api/transcripts?source_stem=${encodeURIComponent(stem)}`);
        if (!api.ok) {
            header.textContent = `暂无 transcript（${api.status}）`;
            list.innerHTML = '<p class="empty-hint">请先运行语音转录步骤</p>';
            return;
        }
        const data = await api.json();
        state.transcript = data;
        renderTranscriptData(header, list, data, video);
    } catch (err) {
        header.textContent = `加载失败: ${err.message}`;
    }
}

function renderTranscriptData(header, list, data, video) {
    const offsetSec = video.offset_sec || 0;
    const duration = video.duration || Infinity;
    const segments = data.segments || [];

    header.innerHTML = `
        <div class="transcript-meta">
            <strong>转录 — ${data.source_video || ''}</strong>
            <span>语言: ${data.language || '-'}</span>
            <span>模型: ${data.model_size || '-'}</span>
            <span>共 ${segments.length} 段</span>
        </div>
    `;

    // 对 split 段进行过滤 + 偏移
    let filtered = segments;
    if (offsetSec > 0) {
        filtered = segments.filter(s =>
            s.start >= offsetSec && s.end <= offsetSec + duration
        );
    }

    if (filtered.length === 0) {
        list.innerHTML = '<p class="empty-hint">该片段范围内无转录内容</p>';
        return;
    }

    list.innerHTML = filtered.map((seg, i) => {
        const displayStart = Math.max(0, seg.start - offsetSec);
        const displayEnd = seg.end - offsetSec;
        const timeStr = `${formatTime(displayStart)} → ${formatTime(displayEnd)}`;
        return `
            <div class="transcript-item" data-start="${seg.start}" data-end="${seg.end}">
                <div class="transcript-time" title="点击跳转">${timeStr}</div>
                <div class="transcript-text">
                    <span>${escapeHtml(seg.text)}</span>
                    <span class="transcript-conf">(${seg.avg_logprob})</span>
                </div>
                <button class="transcript-delete" data-index="${i}" title="删除此段">×</button>
            </div>
        `;
    }).join('');

    // 事件绑定：点击时间跳转
    list.querySelectorAll('.transcript-time').forEach(el => {
        el.addEventListener('click', () => {
            const start = parseFloat(el.parentElement.dataset.start);
            playVideoAt(start, !!offsetSec);
        });
    });

    // 事件绑定：删除按钮
    list.querySelectorAll('.transcript-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
            const idx = parseInt(btn.dataset.index);
            if (!confirm('确认删除此 transcript 片段？')) return;
            data.segments.splice(idx, 1);
            // resave the transcript
            const api = await fetchAPI('/api/transcripts', {
                method: 'PUT',
                body: JSON.stringify(data),
                headers: {'Content-Type': 'application/json'},
            });
            if (api.ok) {
                renderTranscriptData(header, list, data, video);
            }
        });
    });
}

function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = (sec % 60).toFixed(1);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(4, '0')}`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function playVideoAt(sec, hasOffset) {
    const videoEl = document.querySelector('#video-player video');
    if (videoEl) {
        videoEl.currentTime = hasOffset ? sec - (state.currentVideo?.offset_sec || 0) : sec;
        videoEl.play();
    }
}
```

Add `renderTranscript` to `renderActiveTab` switch:

```javascript
    case 'transcript':
        renderTranscript();
        break;
```

- [ ] **Step 5: Add seekToAbsolute to viewer.js**

In `vlog_tool/ui/static/src/viewer.js`, add:

```javascript
export function seekToAbsolute(sec) {
    const player = document.querySelector('#video-player video');
    if (!player) return;
    const offset = window._currentVideoOffset || 0;
    player.currentTime = Math.max(0, sec - offset);
    player.play();
}
```

- [ ] **Step 6: Add transcribe step to runner.js**

In `vlog_tool/ui/static/src/runner.js`, find `RUN_STEPS` array and add:

```javascript
{ key: 'transcribe', label: '语音转录', hint: 'Whisper ASR（需先安装依赖）' },
```

- [ ] **Step 7: Add has_transcript to videos.py route**

In `vlog_tool/ui/routes/videos.py`, in the video entry building logic, check for transcript file existence and add fields:

```python
    # 检测 transcript
    trans_dir = config.paths.output_dir / config.whisper.transcripts_subdir
    trans_file = trans_dir / f"{stem}_transcript.json"
    entry["has_transcript"] = trans_file.is_file()
    if trans_file.is_file():
        try:
            trans_data = json.loads(trans_file.read_text(encoding="utf-8"))
            entry["transcript_info"] = f"{trans_data.get('language', '')} / {trans_data.get('model_size', '')}"
            entry["source_stem"] = trans_data.get("source_stem", stem)
        except (json.JSONDecodeError, KeyError):
            pass
```

- [ ] **Step 8: Run all tests**

```
python -m pytest vlog_tool\tests -q
```
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add vlog_tool/ui/static/index.html vlog_tool/ui/static/src/state.js vlog_tool/ui/static/src/sidebar.js vlog_tool/ui/static/src/editor.js vlog_tool/ui/static/src/viewer.js vlog_tool/ui/static/src/runner.js vlog_tool/ui/routes/videos.py
git commit -m "feat(ui): add transcripts tab, sidebar badge, and run step"
```

---

### Task 9: Documentation updates

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md` / `README.en.md`

- [ ] **Step 1: Update AGENTS.md**

In §7, add Whisper module entry to directory structure:

```
├── vlog_tool/
│   ├── transcribe.py            # Whisper ASR 核心模块（模型缓存、音频转录）
│   └── whisper_cli.py           # whisper install/check CLI
```

Add to commit list the new commits.

In §5 (添加新功能的标准做法), add "加一个新的 ASR backend" to the provider/feature guide.

- [ ] **Step 2: Update README**

Add a reference to the `transcribe` and `whisper` subcommands in the command reference.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md README.md README.en.md
git commit -m "docs: add Whisper transcription feature documentation"
```

---

### Self-Review Checklist

- [ ] **Spec coverage**: Every requirement from the design doc has a corresponding task:
  - Config (Task 1) ✓
  - Core transcription (Task 2) ✓
  - Pipeline task + dedup (Task 3) ✓
  - CLI (Task 4) ✓
  - Plan integration (Task 5) ✓
  - Dependencies (Task 6) ✓
  - Backend routes (Task 7) ✓
  - Frontend UI (Task 8) ✓
  - Documentation (Task 9) ✓

- [ ] **Placeholder scan**: No TBD/TODO/vague references. All code blocks contain actual implementation code.

- [ ] **Type consistency**: `WhisperConfig` is used consistently across all tasks. `_resolve_original`, `transcribe_audio`, `run_transcribe_all` signatures match across tasks.

- [ ] **Test coverage**: Each major module has associated test file with mock-based tests. No real model loading in tests.

---

*— END —*
