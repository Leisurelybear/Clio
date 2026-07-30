# clio/desktop/app.py
"""pywebview host entry: start localhost UI server, open native window, js_api pickers."""

from __future__ import annotations

import sys
from pathlib import Path


def main(
    argv: list[str] | None = None,
    config_path: str | Path | None = None,
) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Optional argv/--config parsing refined later; v1 uses config_path or cwd default.
    _ = argv
    if config_path is None:
        config_path = Path("config.yaml")
    else:
        config_path = Path(config_path)

    from clio.config import load_config
    from clio.desktop.api import DesktopApi
    from clio.desktop.server_host import start_server, stop_server

    cfg_file = config_path if config_path.is_file() else None
    cfg = load_config(str(config_path) if cfg_file else "config.yaml")
    config_dir = config_path.parent.resolve() if cfg_file else Path.cwd()

    handle = start_server(
        cfg,
        config_path=cfg_file,
        host="127.0.0.1",
        port=0,
        api_token=None,
    )
    url = f"http://{handle.host}:{handle.port}/"
    try:
        import webview

        api = DesktopApi(config_dir)
        window = webview.create_window(
            "Clio",
            url,
            js_api=api,
            width=1280,
            height=800,
        )

        # Close policy refined in Task 11; v1: stop server on window closed.
        def _on_closed() -> None:
            stop_server(handle)

        try:
            window.events.closed += _on_closed
        except Exception:  # noqa: BLE001 — event API may differ by version
            pass
        webview.start()
    finally:
        stop_server(handle)
    return 0
