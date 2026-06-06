from __future__ import annotations

import httpx

from vlog_tool.config import ProviderConfig, ProxyConfig


class OpenAICompatProvider:
    """OpenAI 及兼容 API（DeepSeek、通义、Moonshot 等）。"""

    provider_id = "openai_compat"

    def __init__(self, cfg: ProviderConfig, proxy: ProxyConfig):
        if not cfg.api_key:
            raise ValueError(
                f"Provider '{cfg.name}' 缺少 API Key，请设置环境变量 {cfg.api_key_env}"
            )
        self._api_key = cfg.api_key
        self._base_url = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        client_kwargs: dict = {"timeout": 120.0}
        if proxy.enabled and proxy.url:
            client_kwargs["proxy"] = proxy.url
        self._client = httpx.Client(**client_kwargs)

    def generate_text(self, prompt: str, model: str) -> str:
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
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def analyze_video(self, video_path: str, prompt: str, model: str) -> str:
        raise NotImplementedError(
            f"Provider '{self.provider_id}' 不支持视频分析，"
            "请将 ai.tasks.video_analyze 配置为 gemini 类型厂家"
        )
