# clio/desktop/app.py
"""pywebview host entry: start localhost UI server, open native window, js_api pickers."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from clio.desktop.server_host import fetch_run_status, request_run_cancel


def _confirm_quit() -> bool:
    """Native askyesno. Returns True (quit) when the user confirms or tkinter fails."""
    try:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return messagebox.askyesno("退出 Clio", "任务仍在运行，确定退出？")
        finally:
            root.destroy()
    except Exception:  # noqa: BLE001 — never block quit on dialog failure
        return True


def _handle_closing(
    host: str,
    port: int,
    confirm_quit: Callable[[], bool] | None = None,
) -> bool:
    """Close policy: abort close while a run is active unless the user confirms.

    Returns True to allow the window to close, False to cancel the close request.
    """
    if confirm_quit is None:
        confirm_quit = _confirm_quit
    status = fetch_run_status(host, port)
    if status.get("running"):
        if not confirm_quit():
            return False
        request_run_cancel(host, port)
    return True


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

        # Close policy (Task 12): cancel active run before closing the window.
        def _on_closing() -> bool:
            return _handle_closing(handle.host, handle.port)

        def _on_closed() -> None:
            stop_server(handle)

        try:
            window.events.closing += _on_closing
        except Exception:  # noqa: BLE001 — event API may differ by version
            pass
        try:
            window.events.closed += _on_closed
        except Exception:  # noqa: BLE001 — event API may differ by version
            pass
        webview.start()
    finally:
        stop_server(handle)
    return 0
