from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import nullcontext

import httpx
from google import genai
from google.genai import types

from vlog_tool.config import ProviderConfig, ProxyConfig
from vlog_tool.ratelimit import make_rate_limiter
from vlog_tool.utils import mask_if_looks_like_key, with_retry

try:
    from google.genai import errors as _genai_errors

    _HAS_GENAI_ERRORS = True
except ImportError:
    _HAS_GENAI_ERRORS = False


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
        self._rl = make_rate_limiter(cfg.requests_per_minute)
        self._poll_interval = cfg.poll_interval_sec
        self._retry_attempts = cfg.retry_attempts

    def _is_retryable(self, exc: BaseException) -> bool:
        """判断异常是否应该重试。"""
        if isinstance(exc, OSError):
            return True
        if _HAS_GENAI_ERRORS:
            if isinstance(exc, _genai_errors.ServerError):
                return True
            if isinstance(exc, _genai_errors.ClientError):
                code = getattr(exc, "code", None)
                if code == 429:
                    return True
                status = getattr(exc, "status", "") or ""
                if "RATE_LIMIT" in status.upper() or "RESOURCE_EXHAUSTED" in status.upper():
                    return True
                return False
        return False

    def _retryable_types(self):
        """返回 with_retry 需要的异常类型元组。"""
        types_list = [OSError]
        if _HAS_GENAI_ERRORS:
            types_list.append(_genai_errors.ClientError)
            types_list.append(_genai_errors.ServerError)
        return tuple(types_list)

    def _call_with_retry(self, fn, what, model):
        """统一的重试入口：将非重试 ClientError 转成 RuntimeError 避免误重试。"""

        def _wrapped():
            try:
                return fn()
            except BaseException as e:
                if self._is_retryable(e):
                    raise
                raise RuntimeError(f"Gemini API 不可重试错误: {e}") from e

        return with_retry(
            _wrapped,
            attempts=self._retry_attempts,
            base_delay=2.0,
            retry_on=self._retryable_types(),
            what=f"Gemini {what}",
            # 用 should_retry 进一步过滤：只有 _is_retryable 为 True 才重试
            should_retry=lambda e: self._is_retryable(e),
        )

    def _wait_for_file(self, uploaded, timeout: float = 300, on_progress: Callable[[str], None] | None = None):
        deadline = time.monotonic() + timeout
        while uploaded.state == types.FileState.PROCESSING:
            if time.monotonic() > deadline:
                raise TimeoutError(f"视频处理超时（{timeout}s）: {uploaded.name}")
            waited = int(time.monotonic() - (deadline - timeout))
            if on_progress:
                on_progress(f"等待 Gemini 处理（{waited}s）...")
            print(f"  视频处理中...（{waited}s）")
            time.sleep(self._poll_interval)
            uploaded = self._client.files.get(name=uploaded.name)
        if uploaded.state == types.FileState.FAILED:
            raise RuntimeError(f"视频处理失败: {uploaded.name}")
        return uploaded

    def generate_text(self, prompt: str, model: str) -> str:
        rl_ctx = self._rl or nullcontext()

        def _do() -> str:
            with rl_ctx:
                response = self._client.models.generate_content(model=model, contents=prompt)
            return response.text or ""

        return self._call_with_retry(_do, model, model)

    def analyze_video(
        self, video_path: str, prompt: str, model: str, progress_callback: Callable[[str], None] | None = None
    ) -> str:
        uploaded = None
        rl_ctx = self._rl or nullcontext()
        try:
            if progress_callback:
                progress_callback("上传视频到 Gemini...")
            with rl_ctx:
                uploaded = self._client.files.upload(file=video_path)
            if progress_callback:
                progress_callback("等待 Gemini 处理...")
            uploaded = self._wait_for_file(uploaded, on_progress=progress_callback)

            if progress_callback:
                progress_callback("AI 分析中...")

            def _do() -> str:
                with rl_ctx:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=[uploaded, prompt],
                    )
                return response.text or ""

            return self._call_with_retry(_do, f"视频 {model}", model)
        finally:
            if uploaded is not None:
                try:
                    self._client.files.delete(name=uploaded.name)
                except Exception:
                    pass
