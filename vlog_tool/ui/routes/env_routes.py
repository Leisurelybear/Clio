"""Route handlers: GET/PUT /api/env — .env file viewer/saver."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vlog_tool.config import _load_dotenv

if TYPE_CHECKING:
    from vlog_tool.ui.handler_protocol import HandlerProtocol


def _dotenv_path(handler: HandlerProtocol) -> Path | None:
    config_path: Path | None = handler.config_path
    if config_path and config_path.is_file():
        return config_path.parent / ".env"
    return None


def handle_get_env(handler: HandlerProtocol, qs: dict[str, str]) -> None:
    env_path = _dotenv_path(handler)
    if env_path and env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
    else:
        text = (
            "# 在此设置环境变量，每行 KEY=VALUE\n"
            "# 示例:\n"
            "# DEEPSEEK_API_KEY=your_key_here\n"
            "# GEMINI_API_KEY=your_key_here\n"
        )
    handler._send_json({"path": str(env_path) if env_path else "", "content": text})


def handle_put_env(handler: HandlerProtocol, qs: dict[str, str], obj: dict) -> None:
    env_path = _dotenv_path(handler)
    if not env_path:
        return handler._send_json({"ok": False, "error": "config_path not available"}, 500)
    content = obj.get("content", "")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(content, encoding="utf-8")
    # Reload env vars into os.environ so subsequent load_config picks them up
    _load_dotenv(env_path.parent, override=True)
    # Clear config cache so next request rebuilds with the new API keys
    handler.__class__._config_cache.invalidate_all()
    handler._send_json({"ok": True, "path": str(env_path)})
