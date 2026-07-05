from clio.config.models import AppConfig


def _filter_dc(raw: dict, dc: type) -> dict:
    fields = set()
    if hasattr(dc, "__dataclass_fields__"):
        fields = {f.name for f in dc.__dataclass_fields__.values()}
    return {k: v for k, v in raw.items() if k in fields}


def _require_min(field_name: str, value: int | float, minimum: int | float) -> None:
    if value < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}, got: {value}")


def _validate_config(config: AppConfig) -> None:
    if config.proxy.enabled and not config.proxy.url:
        raise ValueError(
            "proxy.enabled=true 但 proxy.url 为空。请填写 url（如 socks5://127.0.0.1:1080），或把 enabled 改成 false。"
        )
    _require_min("analyze.max_workers", config.analyze.max_workers, 1)
    _require_min("compress.target_size_mb", config.compress.target_size_mb, 0.01)
    _require_min("compress.max_width", config.compress.max_width, 1)
    _require_min("compress.split_max_min", config.compress.split_max_min, 0)
    _require_min("naming.index_width", config.naming.index_width, 1)
    _require_min("ai.provider_ttl_min", config.ai.provider_ttl_min, 0)
    provider_names = set(config.ai.providers)
    for provider_name, provider_cfg in config.ai.providers.items():
        _require_min(f"ai.providers.{provider_name}.requests_per_minute", provider_cfg.requests_per_minute, 0)
        _require_min(f"ai.providers.{provider_name}.retry_attempts", provider_cfg.retry_attempts, 0)
        _require_min(f"ai.providers.{provider_name}.max_tokens", provider_cfg.max_tokens, 1)
    for task_name, task_cfg in config.ai.tasks.items():
        if task_cfg.provider not in provider_names:
            available = ", ".join(sorted(provider_names)) or "<无>"
            raise ValueError(
                f"ai.tasks.{task_name}.provider = '{task_cfg.provider}'，"
                f"但 ai.providers 里没有这个名字。"
                f"已配置的厂家: {available}。"
                "请检查拼写，或在 ai.providers 里补上对应厂家。"
            )
