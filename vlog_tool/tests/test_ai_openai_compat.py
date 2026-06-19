from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from vlog_tool.config import ProviderConfig, ProxyConfig


def _make_cfg(**kwargs) -> ProviderConfig:
    defaults = dict(
        name="deepseek",
        type="openai",
        api_key="sk-test-key",
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        requests_per_minute=0,
        poll_interval_sec=5,
        retry_attempts=2,
        max_tokens=4096,
    )
    defaults.update(kwargs)
    return ProviderConfig(**defaults)


@pytest.fixture
def proxy_disabled():
    return ProxyConfig(enabled=False, url="")


@pytest.fixture
def proxy_enabled():
    return ProxyConfig(enabled=True, url="http://proxy:8080")


class TestInit:
    def test_missing_api_key_raises(self):
        cfg = _make_cfg(api_key="")
        with pytest.raises(ValueError, match="缺少 API Key"):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            OpenAICompatProvider(cfg, ProxyConfig(enabled=False, url=""))

    def test_default_base_url(self, proxy_disabled):
        cfg = _make_cfg(base_url="")
        with patch("vlog_tool.ai.openai_compat.httpx.Client"):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            p = OpenAICompatProvider(cfg, proxy_disabled)
            assert "api.openai.com/v1" in p._base_url

    def test_uses_custom_base_url(self, proxy_disabled):
        with patch("vlog_tool.ai.openai_compat.httpx.Client"):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            p = OpenAICompatProvider(_make_cfg(), proxy_disabled)
            assert p._base_url == "https://api.deepseek.com"

    def test_strips_trailing_slash(self, proxy_disabled):
        with patch("vlog_tool.ai.openai_compat.httpx.Client"):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            p = OpenAICompatProvider(_make_cfg(base_url="https://api.deepseek.com/"), proxy_disabled)
            assert p._base_url == "https://api.deepseek.com"

    def test_creates_client_without_proxy(self, proxy_disabled):
        with patch("vlog_tool.ai.openai_compat.httpx.Client") as mock_cls:
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            OpenAICompatProvider(_make_cfg(), proxy_disabled)
            mock_cls.assert_called_once_with(timeout=120.0)

    def test_creates_client_with_proxy(self, proxy_enabled):
        with patch("vlog_tool.ai.openai_compat.httpx.Client") as mock_cls:
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            OpenAICompatProvider(_make_cfg(), proxy_enabled)
            mock_cls.assert_called_once_with(timeout=120.0, proxy="http://proxy:8080")

    def test_rate_limiter_disabled(self, proxy_disabled):
        with patch("vlog_tool.ai.openai_compat.httpx.Client"):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            p = OpenAICompatProvider(_make_cfg(requests_per_minute=0), proxy_disabled)
            assert p._rl is None

    def test_rate_limiter_enabled(self, proxy_disabled):
        with patch("vlog_tool.ai.openai_compat.httpx.Client"):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            p = OpenAICompatProvider(_make_cfg(requests_per_minute=10), proxy_disabled)
            assert p._rl is not None


class TestClose:
    def test_closes_http_client(self):
        mock_client = MagicMock()
        with patch("vlog_tool.ai.openai_compat.httpx.Client", return_value=mock_client):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            p = OpenAICompatProvider(_make_cfg(), ProxyConfig(enabled=False, url=""))
            p.close()
            mock_client.close.assert_called_once()


class TestGenerateText:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self._mock_client = MagicMock()
        with patch("vlog_tool.ai.openai_compat.httpx.Client", return_value=self._mock_client):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            self._prov = OpenAICompatProvider(_make_cfg(), ProxyConfig(enabled=False, url=""))
            yield

    def _mock_response(self, status_code=200, text='{"choices":[{"message":{"content":"ok"}}]}'):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.text = text
        resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        return resp

    def test_success(self):
        resp = self._mock_response()
        self._mock_client.post.return_value = resp

        result = self._prov.generate_text("hello", "deepseek-chat")
        assert result == "ok"
        self._mock_client.post.assert_called_once()

    def test_sends_correct_payload(self):
        resp = self._mock_response()
        self._mock_client.post.return_value = resp

        self._prov.generate_text("hello", "deepseek-chat")
        call_kwargs = self._mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "deepseek-chat"
        assert call_kwargs["json"]["messages"][0]["content"] == "hello"
        assert call_kwargs["json"]["max_tokens"] == 4096
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key"

    def test_429_raises_http_status_error(self):
        resp = self._mock_response(status_code=429)
        self._mock_client.post.return_value = resp

        with pytest.raises(httpx.HTTPStatusError):
            self._prov.generate_text("hello", "deepseek-chat")

    def test_500_raises_http_status_error(self):
        resp = self._mock_response(status_code=500)
        self._mock_client.post.return_value = resp

        with pytest.raises(httpx.HTTPStatusError):
            self._prov.generate_text("hello", "deepseek-chat")

    def test_400_raises_value_error(self):
        resp = self._mock_response(status_code=400, text='{"error":"bad request"}')
        self._mock_client.post.return_value = resp

        with pytest.raises(ValueError, match="400"):
            self._prov.generate_text("hello", "deepseek-chat")

    def test_404_raises_value_error(self):
        resp = self._mock_response(status_code=404, text="not found")
        self._mock_client.post.return_value = resp

        with pytest.raises(ValueError, match="404"):
            self._prov.generate_text("hello", "deepseek-chat")

    def test_connection_error_retries(self):
        self._mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(httpx.ConnectError):
            self._prov.generate_text("hello", "deepseek-chat")
        assert self._mock_client.post.call_count >= 2

    def test_uses_correct_url(self):
        resp = self._mock_response()
        self._mock_client.post.return_value = resp

        self._prov.generate_text("hello", "deepseek-chat")
        call_url = self._mock_client.post.call_args.args[0]
        assert call_url == "https://api.deepseek.com/chat/completions"


class TestAnalyzeVideo:
    def test_not_implemented(self):
        with patch("vlog_tool.ai.openai_compat.httpx.Client"):
            from vlog_tool.ai.openai_compat import OpenAICompatProvider

            p = OpenAICompatProvider(_make_cfg(), ProxyConfig(enabled=False, url=""))
            with pytest.raises(NotImplementedError, match="不支持视频分析"):
                p.analyze_video("video.mp4", "desc", "model")
