"""Route handlers: /api/fs/dirs"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler

from vlog_tool.ui.services.file_service import _list_drives


def handle_get_fs_dirs(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/fs/dirs."""
    dir_path = qs.get("path", [""])[0]
    if not dir_path:
        if sys.platform == "win32":
            drives = _list_drives()
            return handler._send_json({"path": "", "dirs": drives, "parent": None, "is_drive_list": True})
        return handler._send_json({"path": "/", "dirs": ["/"], "parent": None, "is_drive_list": True})
    try:
        resolved = Path(dir_path).resolve()
        if not resolved.is_dir():
            return handler._send_json({"error": "not a directory"}, 400)
        dirs: list[str] = []
        try:
            with os.scandir(resolved) as it:
                for entry in it:
                    if entry.is_dir() and not entry.name.startswith("."):
                        dirs.append(entry.path)
        except PermissionError:
            pass
        dirs.sort(key=lambda x: Path(x).name.lower())
        parent = str(resolved.parent) if resolved.parent != resolved else None
        return handler._send_json(
            {
                "path": str(resolved),
                "dirs": dirs,
                "parent": parent,
                "is_drive_list": False,
            }
        )
    except PermissionError:
        return handler._send_json({"error": "access denied"}, 403)
    except OSError as e:
        return handler._send_json({"error": str(e)}, 500)
