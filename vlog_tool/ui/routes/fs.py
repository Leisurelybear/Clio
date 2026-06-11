"""Route handlers: /api/fs/dirs"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_get_fs_dirs(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    """Handle GET /api/fs/dirs."""
    import sys

    dir_path = qs.get("path", [""])[0]
    if not dir_path:
        from vlog_tool.ui.services.file_service import _list_drives

        if sys.platform == "win32":
            drives = _list_drives()
            return handler._send_json({"path": "", "dirs": drives, "parent": None, "is_drive_list": True})
        return handler._send_json({"path": "/", "dirs": ["/"], "parent": None, "is_drive_list": True})
    try:
        p = Path(dir_path).resolve()
        if not p.is_dir():
            return handler._send_json({"error": "not a directory"}, 400)
        dirs: list[str] = []
        try:
            with os.scandir(p) as it:
                for entry in it:
                    if entry.is_dir() and not entry.name.startswith("."):
                        dirs.append(entry.path)
        except PermissionError:
            pass
        dirs.sort(key=lambda x: Path(x).name.lower())
        parent = str(p.parent) if p.parent != p else None
        return handler._send_json(
            {
                "path": str(p),
                "dirs": dirs,
                "parent": parent,
                "is_drive_list": False,
            }
        )
    except PermissionError:
        return handler._send_json({"error": "access denied"}, 403)
    except OSError as e:
        return handler._send_json({"error": str(e)}, 500)
