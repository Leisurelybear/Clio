from __future__ import annotations

import httpx

from vlog_tool.config import ProviderConfig, ProxyConfig
from vlog_tool.utils import mask_if_looks_like_key, with_retry


class OpenAICompatProvider:
    """OpenAI 及兼容 API（DeepSeek、通义、Moonshot 等）。"""

    provider_id = "openai_compat"

    def __init__(self, cfg: ProviderConfig, proxy: ProxyConfig):
        if not cfg.api_key:
            env_name = mask_if_looks_like_key(cfg.api_key_env) or "<未设置>"
            raise ValueError(
                f"Provider '{cfg.name}' 缺少 API Key。\n"
                f"  方法 1: 在 .env 中设置环境变量 {env_name}=你的key\n"
                f"  方法 2: 在 config.yaml 的 providers.{cfg.name}.api_key 字段直接填入 key\n"
                f"  （如果误把 key 填到了 api_key_env 字段，请改回环境变量名）"
            )
        self._api_key = cfg.api_key
        self._base_url = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        client_kwargs: dict = {"timeout": 120.0}
        if proxy.enabled and proxy.url:
            client_kwargs["proxy"] = proxy.url
        self._client = httpx.Client(**client_kwargs)

    def generate_text(self, prompt: str, model: str) -> str:
        def _do() -> str:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            sc = response.status_code
            if sc == 429 or sc >= 500:
                raise httpx.HTTPStatusError(
                    f"status {sc}", request=response.request, response=response
                )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

        return with_retry(
            _do,
            attempts=3,
            base_delay=1.0,
            retry_on=(httpx.HTTPError,),
            what=f"OpenAI 兼容 {self._base_url}",
        )

    def analyze_video(self, video_path: str, prompt: str, model: str) -> str:
        raise NotImplementedError(
            f"Provider '{self.provider_id}' 不支持视频分析，"
            "请将 ai.tasks.video_analyze 配置为 gemini 类型厂家"
        )
