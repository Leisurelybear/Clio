from clio.config.models import AppConfig


def _filter_dc(raw: dict, dc: type) -> dict:
    fields = set()
    if hasattr(dc, "__dataclass_fields__"):
        fields = {f.name for f in dc.__dataclass_fields__.values()}
    return {k: v for k, v in raw.items() if k in fields}


def _validate_config(config: AppConfig) -> None:
    if config.proxy.enabled and not config.proxy.url:
        raise ValueError(
            "proxy.enabled=true 但 proxy.url 为空。请填写 url（如 socks5://127.0.0.1:1080），或把 enabled 改成 false。"
        )
    provider_names = set(config.ai.providers)
    for task_name, task_cfg in config.ai.tasks.items():
        if task_cfg.provider not in provider_names:
            available = ", ".join(sorted(provider_names)) or "<无>"
            raise ValueError(
                f"ai.tasks.{task_name}.provider = '{task_cfg.provider}'，"
                f"但 ai.providers 里没有这个名字。"
                f"已配置的厂家: {available}。"
                "请检查拼写，或在 ai.providers 里补上对应厂家。"
            )
