from __future__ import annotations

import time

import httpx
from google import genai
from google.genai import types

from vlog_tool.config import ProviderConfig, ProxyConfig
from vlog_tool.utils import mask_if_looks_like_key, with_retry

try:
    from google.genai import errors as _genai_errors
    _RETRY_ON: tuple[type[BaseException], ...] = (_genai_errors.ServerError, OSError)
except ImportError:
    _RETRY_ON = (OSError,)


class GeminiProvider:
    provider_id = "gemini"

    def __init__(self, cfg: ProviderConfig, proxy: ProxyConfig):
        if not cfg.api_key:
            env_name = mask_if_looks_like_key(cfg.api_key_env) or "<未设置>"
            raise ValueError(
                f"Provider '{cfg.name}' 缺少 API Key。\n"
                f"  方法 1: 在 .env 中设置环境变量 {env_name}=你的key\n"
                f"  方法 2: 在 config.yaml 的 providers.{cfg.name}.api_key 字段直接填入 key\n"
                f"  （如果误把 key 填到了 api_key_env 字段，请改回环境变量名）"
            )
        http_options = None
        if proxy.enabled and proxy.url:
            http_options = types.HttpOptions(
                client_args={"transport": httpx.HTTPTransport(proxy=proxy.url)},
                async_client_args={"transport": httpx.AsyncHTTPTransport(proxy=proxy.url)},
            )
        self._client = genai.Client(api_key=cfg.api_key, http_options=http_options)
        self._poll_interval = cfg.poll_interval_sec

    def _wait_for_file(self, uploaded):
        while uploaded.state == types.FileState.PROCESSING:
            print("  视频处理中...")
            time.sleep(self._poll_interval)
            uploaded = self._client.files.get(name=uploaded.name)
        if uploaded.state == types.FileState.FAILED:
            raise RuntimeError(f"视频处理失败: {uploaded.name}")
        return uploaded

    def generate_text(self, prompt: str, model: str) -> str:
        def _do() -> str:
            response = self._client.models.generate_content(model=model, contents=prompt)
            return response.text or ""

        return with_retry(
            _do,
            attempts=3,
            base_delay=1.0,
            retry_on=_RETRY_ON,
            what=f"Gemini {model}",
        )

    def analyze_video(self, video_path: str, prompt: str, model: str) -> str:
        # Upload once outside retry — B-002: avoid re-upload on transient errors
        uploaded = self._client.files.upload(file=video_path)
        uploaded = self._wait_for_file(uploaded)

        def _do() -> str:
            response = self._client.models.generate_content(
                model=model,
                contents=[uploaded, prompt],
            )
            return response.text or ""

        try:
            return with_retry(
                _do,
                attempts=3,
                base_delay=1.0,
                retry_on=_RETRY_ON,
                what=f"Gemini 视频 {model}",
            )
        finally:
            # B-001: always clean up uploaded files to avoid quota exhaustion
            if uploaded is not None:
                try:
                    self._client.files.delete(name=uploaded.name)
                except Exception:
                    pass
