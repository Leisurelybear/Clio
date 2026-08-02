# clio/desktop/single_instance.py
"""Single-instance coordination for the desktop shell.

A JSON lock file (``clio.lock``) in the config dir records the first
instance's server port. A second instance decides liveness by POSTing the
focus endpoint: any HTTP response proves the first instance is alive, while a
connection error means the lock is stale and can be taken over. PID checks are
deliberately avoided because os.kill(pid, 0) is unreliable on Windows.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

LOCK_FILENAME = "clio.lock"
WEB_PORT = 8765
_WEB_MARKER = b"Vlog"


def lock_path(config_dir: Path) -> Path:
    return Path(config_dir) / LOCK_FILENAME


def read_lock(config_dir: Path) -> dict | None:
    p = lock_path(config_dir)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    port = data.get("port")
    if not isinstance(port, int) or isinstance(port, bool):
        return None
    return data


def write_lock(config_dir: Path, port: int, pid: int) -> None:
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    payload = {"port": int(port), "pid": int(pid)}
    lock_path(config_dir).write_text(
        json.dumps(payload, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def remove_lock(config_dir: Path) -> None:
    try:
        lock_path(config_dir).unlink()
    except OSError:
        pass


def focus_first_instance(host: str, port: int, timeout: float = 3.0) -> bool:
    """Ask the first instance to focus its window.

    Returns True when any HTTP response is received (the first instance is
    alive — including 5xx while its window is still starting up). Returns
    False only when the server is unreachable (stale lock / connection error).
    """
    try:
        req = urllib.request.Request(
            f"http://{host}:{port}/api/desktop/focus",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def is_web_running(host: str = "127.0.0.1", port: int = WEB_PORT, timeout: float = 2.0) -> bool:
    """Return True when the web UI (``serve``) is already up on the default port."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=timeout) as resp:
            if resp.status != 200:
                return False
            return _WEB_MARKER in resp.read(1024)
    except OSError:
        return False
