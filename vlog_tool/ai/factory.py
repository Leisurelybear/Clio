from __future__ import annotations

import threading

from vlog_tool.ai.base import TaskName, TextAIProvider, VideoAIProvider
from vlog_tool.ai.gemini import GeminiProvider
from vlog_tool.ai.openai_compat import OpenAICompatProvider
from vlog_tool.config import AppConfig, TaskConfig

_PROVIDER_TYPES = {
    "gemini": GeminiProvider,
    "openai": OpenAICompatProvider,
    "openai_compat": OpenAICompatProvider,
}

_provider_cache: dict[tuple, TextAIProvider] = {}
_provider_cache_lock = threading.Lock()


def _build_provider(config: AppConfig, provider_name: str):
    provider_cfg = config.ai.providers.get(provider_name)
    if not provider_cfg:
        raise ValueError(f"未定义的 AI 厂家: {provider_name}")
    cache_key = (
        provider_name,
        provider_cfg.api_key,
        provider_cfg.base_url,
        provider_cfg.type,
        provider_cfg.poll_interval_sec,
        config.proxy.url,
        config.proxy.enabled,
    )
    with _provider_cache_lock:
        cached = _provider_cache.get(cache_key)
        if cached is not None:
            return cached
    cls = _PROVIDER_TYPES.get(provider_cfg.type)
    if not cls:
        raise ValueError(f"不支持的厂家类型 '{provider_cfg.type}'，可选: {', '.join(_PROVIDER_TYPES)}")
    provider = cls(provider_cfg, config.proxy)
    with _provider_cache_lock:
        existing = _provider_cache.get(cache_key)
        if existing is not None:
            provider.close()
            return existing
        _provider_cache[cache_key] = provider
    return provider


def _clear_provider_cache() -> None:
    """Close all cached providers and clear the cache (for testing / config reload)."""
    with _provider_cache_lock:
        providers = list(_provider_cache.values())
        _provider_cache.clear()
    for p in providers:
        try:
            p.close()
        except Exception:
            pass


def get_task_config(config: AppConfig, task: TaskName | str) -> TaskConfig:
    task_name = task.value if isinstance(task, TaskName) else task
    task_cfg = config.ai.tasks.get(task_name)
    if not task_cfg:
        raise ValueError(f"未配置 AI 任务: {task_name}")
    return task_cfg


def get_task_provider(config: AppConfig, task: TaskName | str) -> tuple[TextAIProvider, str]:
    task_cfg = get_task_config(config, task)
    provider = _build_provider(config, task_cfg.provider)
    return provider, task_cfg.model


def get_video_provider(config: AppConfig, task: TaskName | str) -> tuple[VideoAIProvider, str]:
    provider, model = get_task_provider(config, task)
    if not isinstance(provider, VideoAIProvider):
        raise ValueError(f"任务 '{task}' 使用的厂家不支持视频分析")
    return provider, model
