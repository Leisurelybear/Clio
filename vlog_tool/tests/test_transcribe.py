from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vlog_tool.config import AppConfig, WhisperConfig
from vlog_tool.tasks.transcribe import run_transcribe_all
from vlog_tool.transcribe import (
    _get_model,
    _resolve_cache_dir,
    _resolve_compute_type,
    _resolve_device,
    transcribe_audio,
)


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig(
        paths=MagicMock(),
        whisper=WhisperConfig(enabled=True, model_size="small", language="zh", device="cpu"),
    )


class TestResolveCacheDir:
    def test_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr("vlog_tool.transcribe.PROJECT_ROOT", tmp_path)
        result = _resolve_cache_dir(MagicMock(whisper=WhisperConfig(cache_dir=None)))
        assert result == tmp_path / "models"

    def test_custom(self, tmp_path):
        custom = tmp_path / "whisper_cache"
        result = _resolve_cache_dir(MagicMock(whisper=WhisperConfig(cache_dir=str(custom))))
        assert result == custom


class TestResolveDevice:
    def test_cpu(self):
        assert _resolve_device(MagicMock(whisper=WhisperConfig(device="cpu"))) == "cpu"

    def test_cuda(self):
        assert _resolve_device(MagicMock(whisper=WhisperConfig(device="cuda"))) == "cuda"

    @patch("ctranslate2.get_cuda_device_count")
    def test_auto_cpu(self, mock_cuda_count):
        mock_cuda_count.return_value = 0
        assert _resolve_device(MagicMock(whisper=WhisperConfig(device="auto"))) == "cpu"

    @patch("ctranslate2.get_cuda_device_count")
    def test_auto_cuda(self, mock_cuda_count):
        mock_cuda_count.return_value = 1
        assert _resolve_device(MagicMock(whisper=WhisperConfig(device="auto"))) == "cuda"


class TestResolveComputeType:
    def test_cpu(self):
        assert _resolve_compute_type("cpu") == "int8"

    def test_cuda(self):
        assert _resolve_compute_type("cuda") == "int8_float16"


class TestGetModel:
    @patch("vlog_tool.transcribe.WhisperModel")
    def test_singleton(self, mock_whisper_cls):
        cfg = MagicMock(whisper=WhisperConfig(model_size="small", cache_dir="/cache"))
        with (
            patch("vlog_tool.transcribe._whisper_model", None),
            patch("vlog_tool.transcribe._whisper_cache_key", None),
        ):
            m1 = _get_model(cfg)
            m2 = _get_model(cfg)
            assert m1 is m2
            mock_whisper_cls.assert_called_once()

    @patch("vlog_tool.transcribe.WhisperModel", None)
    @patch("vlog_tool.transcribe._resolve_cache_dir")
    @patch("vlog_tool.transcribe._resolve_device", return_value="cpu")
    def test_get_model_import_error(self, mock_dev, mock_cache):
        """WhisperModel 未安装时抛 ImportError"""
        with pytest.raises(ImportError):
            _get_model(MagicMock(whisper=WhisperConfig(model_size="small")))

    @patch("vlog_tool.transcribe.WhisperModel")
    def test_get_model_cache_invalidation(self, mock_whisper_cls):
        """model_size 或 cache_dir 变化时重新加载模型"""
        mock_whisper_cls.side_effect = lambda *a, **kw: MagicMock()
        cfg1 = MagicMock(whisper=WhisperConfig(model_size="small", cache_dir="/cache1"))
        cfg2 = MagicMock(whisper=WhisperConfig(model_size="medium", cache_dir="/cache1"))
        with (
            patch("vlog_tool.transcribe._whisper_model", None),
            patch("vlog_tool.transcribe._whisper_cache_key", None),
        ):
            m1 = _get_model(cfg1)
            m2 = _get_model(cfg2)
            assert m1 is not m2
            assert mock_whisper_cls.call_count == 2


class TestTranscribeAudio:
    @patch("vlog_tool.transcribe._get_model")
    def test_segments(self, mock_get_model):
        mock_model = MagicMock()
        seg1 = MagicMock(
            start=0.0,
            end=2.5,
            text=" 今天天气真好 ",
            avg_logprob=-0.1,
            no_speech_prob=0.01,
        )
        seg2 = MagicMock(
            start=2.5,
            end=5.0,
            text=" 我们来了 ",
            avg_logprob=-0.3,
            no_speech_prob=0.02,
        )
        seg3 = MagicMock(
            start=5.0,
            end=7.0,
            text=" 低置信度 ",
            avg_logprob=-0.9,
            no_speech_prob=0.5,
        )
        mock_model.transcribe.return_value = (
            [seg1, seg2, seg3],
            MagicMock(language="zh", language_probability=0.95, duration=100.0),
        )
        mock_get_model.return_value = mock_model

        callback = MagicMock()
        result = transcribe_audio(
            Path("/fake.wav"),
            MagicMock(whisper=WhisperConfig(language="zh")),
            callback,
        )

        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[0]["text"] == "今天天气真好"
        assert result[1]["start"] == 2.5
        callback.assert_called()

    @patch("vlog_tool.transcribe._get_model")
    def test_auto_language(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            [],
            MagicMock(language="en", language_probability=0.99, duration=50.0),
        )
        mock_get_model.return_value = mock_model

        result = transcribe_audio(
            Path("/fake.wav"),
            MagicMock(whisper=WhisperConfig(language="auto")),
        )
        assert result == []

        _, kwargs = mock_model.transcribe.call_args
        assert kwargs["language"] is None


class TestRunTranscribeAll:
    def test_transcribe_enabled_check_no_deps(self):
        """当 faster-whisper 不可导入时，run_transcribe_all 打印警告并返回 0"""
        config = AppConfig(
            paths=MagicMock(),
            whisper=WhisperConfig(enabled=True),
        )

        with (
            patch("vlog_tool.tasks.transcribe.check_whisper", return_value=False),
            patch("builtins.print") as mock_print,
        ):
            result = run_transcribe_all(config)
            assert result == 0
            # should have printed some warning

    def test_transcribe_skipped_when_disabled(self):
        """whisper.enabled=False 时跳过转录"""
        config = AppConfig(
            paths=MagicMock(),
            whisper=WhisperConfig(enabled=False),
        )

        with patch("builtins.print") as mock_print:
            result = run_transcribe_all(config)
            assert result == 0
