# clio/desktop/server_host.py
"""Start/stop a localhost UI HTTP server for the desktop shell (non-blocking)."""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

from clio.config import AppConfig
from clio.shutdown import before_stop, install_hooks
from clio.tasks.reindex import auto_reindex_if_needed
from clio.ui.server import make_handler
from clio.ui.services.project_service import resolve_last_project_config


@dataclass
class ServerHandle:
    host: str
    port: int
    server: ThreadingHTTPServer
    thread: threading.Thread


def start_server(
    config: AppConfig,
    config_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    api_token: str | None = None,
) -> ServerHandle:
    """Bind a free (or given) port and serve the UI on a background thread.

    Mirrors ``clio.ui.server.run`` startup (token, project resolve, reindex,
    handler) but never opens a browser and never blocks the caller.
    """
    install_hooks()

    token = api_token
    is_local = host in ("127.0.0.1", "localhost", "")
    if token is None:
        if is_local:
            token = ""
        else:
            token = secrets.token_urlsafe(32)

    active_config = resolve_last_project_config(config, config_path)
    auto_reindex_if_needed(active_config)

    handler = make_handler(active_config, config_path, api_token=token)
    server = ThreadingHTTPServer((host, port), handler)
    bound_host, bound_port = server.server_address[:2]

    thread = threading.Thread(
        target=server.serve_forever,
        name="clio-http",
        daemon=True,
    )
    thread.start()

    return ServerHandle(
        host=str(bound_host),
        port=int(bound_port),
        server=server,
        thread=thread,
    )


def stop_server(handle: ServerHandle, timeout: float = 5.0) -> None:
    """Shut down the HTTP server and join its thread."""
    try:
        handle.server.shutdown()
    finally:
        handle.server.server_close()
        handle.thread.join(timeout=timeout)
        before_stop()
