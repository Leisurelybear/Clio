"""Lightweight security helpers for LAN-mode UI access.

Provides token-based authentication and path restriction for the UI server.
"""

from __future__ import annotations

import os
from pathlib import Path


def _get_ui_token() -> str:
    return os.environ.get("UI_TOKEN", "")


def _is_lan_mode(host: str) -> bool:
    return host not in ("127.0.0.1", "localhost", "")


def _check_token(qs: dict) -> bool:
    token = _get_ui_token()
    if not token:
        return True
    provided = qs.get("token", [None])[0]
    return provided == token


def _restrict_path(p: Path) -> Path | None:
    """Restrict a filesystem path to within the user's home directory.

    Returns the resolved path if allowed, None if outside bounds.
    """
    resolved = p.resolve()
    home = Path.home().resolve()
    if home in resolved.parents or resolved == home:
        return resolved
    return None
