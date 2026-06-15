from __future__ import annotations

from vlog_tool.ai.base import TaskName, TextAIProvider, VideoAIProvider
from vlog_tool.ai.gemini import GeminiProvider
from vlog_tool.ai.openai_compat import OpenAICompatProvider
from vlog_tool.config import AppConfig, TaskConfig

_PROVIDER_TYPES = {
    "gemini": GeminiProvider,
    "openai": OpenAICompatProvider,
    "openai_compat": OpenAICompatProvider,
}

_provider_cache: dict[str, TextAIProvider] = {}


def _build_provider(config: AppConfig, provider_name: str):
    cached = _provider_cache.get(provider_name)
    if cached is not None:
        return cached
    provider_cfg = config.ai.providers.get(provider_name)
    if not provider_cfg:
        raise ValueError(f"未定义的 AI 厂家: {provider_name}")
    cls = _PROVIDER_TYPES.get(provider_cfg.type)
    if not cls:
        raise ValueError(f"不支持的厂家类型 '{provider_cfg.type}'，可选: {', '.join(_PROVIDER_TYPES)}")
    provider = cls(provider_cfg, config.proxy)
    _provider_cache[provider_name] = provider
    return provider


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
