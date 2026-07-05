from clio.config.models import AppConfig

_SUPPORTED_PROVIDER_TYPES = {"gemini", "openai", "openai_compat"}


def _filter_dc(raw: dict, dc: type) -> dict:
    fields = set()
    if hasattr(dc, "__dataclass_fields__"):
        fields = {f.name for f in dc.__dataclass_fields__.values()}
    return {k: v for k, v in raw.items() if k in fields}


def _require_min(field_name: str, value: int | float, minimum: int | float) -> None:
    if value < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}, got: {value}")


def _require_supported_provider_type(provider_name: str, provider_type: str) -> None:
    if provider_type not in _SUPPORTED_PROVIDER_TYPES:
        available = ", ".join(sorted(_SUPPORTED_PROVIDER_TYPES))
        raise ValueError(
            f"ai.providers.{provider_name}.type = '{provider_type}' 不受支持。可选 provider type: {available}。"
        )


def _require_video_provider_compatible(task_name: str, provider_name: str, provider_type: str) -> None:
    if task_name == "video_analyze" and provider_type != "gemini":
        raise ValueError(
            "ai.tasks.video_analyze.provider 必须绑定 gemini 类型 provider。"
            f"'{provider_name}' 当前类型为 '{provider_type}'。"
        )


def _require_known_model(task_name: str, provider_name: str, task_model: str, provider_models: list[str]) -> None:
    if provider_models and task_model not in provider_models:
        available = ", ".join(provider_models)
        raise ValueError(
            f"ai.tasks.{task_name}.model = '{task_model}' 不在 ai.providers.{provider_name}.models 中: {available}。"
        )


def _validate_config(config: AppConfig) -> None:
    if config.proxy.enabled and not config.proxy.url:
        raise ValueError("proxy.enabled=true 但 proxy.url 为空。请填写 proxy.url，或把 proxy.enabled 改成 false。")
    _require_min("analyze.max_workers", config.analyze.max_workers, 1)
    _require_min("compress.target_size_mb", config.compress.target_size_mb, 0.01)
    _require_min("compress.max_width", config.compress.max_width, 1)
    _require_min("compress.split_max_min", config.compress.split_max_min, 0)
    _require_min("naming.index_width", config.naming.index_width, 1)
    _require_min("ai.provider_ttl_min", config.ai.provider_ttl_min, 0)

    provider_names = set(config.ai.providers)
    for provider_name, provider_cfg in config.ai.providers.items():
        _require_supported_provider_type(provider_name, provider_cfg.type)
        _require_min(f"ai.providers.{provider_name}.requests_per_minute", provider_cfg.requests_per_minute, 0)
        _require_min(f"ai.providers.{provider_name}.retry_attempts", provider_cfg.retry_attempts, 0)
        _require_min(f"ai.providers.{provider_name}.max_tokens", provider_cfg.max_tokens, 1)

    for task_name, task_cfg in config.ai.tasks.items():
        if task_cfg.provider not in provider_names:
            available = ", ".join(sorted(provider_names)) or "<无>"
            raise ValueError(
                f"ai.tasks.{task_name}.provider = '{task_cfg.provider}' 不存在。已配置的 provider: {available}。"
            )

        provider_cfg = config.ai.providers[task_cfg.provider]
        _require_video_provider_compatible(task_name, task_cfg.provider, provider_cfg.type)
        _require_known_model(task_name, task_cfg.provider, task_cfg.model, provider_cfg.models)
