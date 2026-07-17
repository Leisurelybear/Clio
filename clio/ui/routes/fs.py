"""Route handlers: /api/fs/dirs, /api/fs/videos, /api/fs/mkdir, /api/fs/reveal"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol

from clio._constants import VIDEO_EXTENSIONS
from clio.ui.services.file_service import _list_drives

# ── security: restrict file-system browsing to known-safe roots ──


def _is_allowed_path(resolved: Path) -> bool:
    """Allow browsing under home, or anywhere on a Windows drive letter.

    Local desktop tool: users need to pick originals on D:/E: etc. Restricting
    to drive roots only made the video manager unusable for external media.
    """
    try:
        if resolved.is_relative_to(Path.home()):
            return True
    except (ValueError, OSError):
        pass
    if sys.platform == "win32":
        # Any path with a drive letter (C:\..., D:\GoPro\..., UNC excluded)
        if resolved.drive:
            return True
    return False


def handle_get_fs_dirs(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/fs/dirs."""
    dir_path = qs.get("path", [""])[0]
    if not dir_path:
        if sys.platform == "win32":
            drives = _list_drives()
            return handler._send_json({"path": "", "dirs": drives, "parent": None, "is_drive_list": True})
        return handler._send_json({"path": "/", "dirs": ["/"], "parent": None, "is_drive_list": True})
    try:
        resolved = Path(dir_path).resolve()
        if not _is_allowed_path(resolved):
            return handler._send_json({"error": "access denied"}, 403)
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


def handle_post_fs_mkdir(handler: HandlerProtocol, obj: dict) -> None:
    """Handle POST /api/fs/mkdir — create a new directory."""
    parent_raw = (obj.get("parent") or "").strip()
    name = (obj.get("name") or "").strip()
    if not parent_raw or not name:
        return handler._send_json({"ok": False, "error": "parent and name required"}, 400)
    if "/" in name or "\\" in name or ".." in name:
        return handler._send_json({"ok": False, "error": "invalid name"}, 400)
    try:
        resolved = Path(parent_raw).resolve()
        if not _is_allowed_path(resolved):
            return handler._send_json({"ok": False, "error": "access denied"}, 403)
        new_dir = resolved / name
        if not _is_allowed_path(new_dir.resolve()):
            return handler._send_json({"ok": False, "error": "access denied"}, 403)
        new_dir.mkdir(parents=True, exist_ok=True)
        return handler._send_json({"ok": True, "path": str(new_dir)})
    except OSError as e:
        return handler._send_json({"ok": False, "error": str(e)}, 500)


def build_reveal_command(path: Path, platform: str | None = None) -> list[str]:
    """CLI used to open a directory in the OS file manager (non-Windows path)."""
    plat = platform if platform is not None else sys.platform
    target = str(path)
    if plat == "darwin":
        return ["open", target]
    return ["xdg-open", target]


def reveal_path_in_file_manager(path: Path) -> Path:
    """Open *path* in Explorer / Finder / file manager. Returns resolved path."""
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"not a directory: {resolved}")
    if sys.platform == "win32":
        # explorer.exe returns non-zero even on success; startfile is reliable.
        os.startfile(str(resolved))  # type: ignore[attr-defined]
        return resolved
    cmd = build_reveal_command(resolved)
    subprocess.run(cmd, check=False)
    return resolved


def handle_post_fs_reveal(handler: HandlerProtocol, obj: dict) -> None:
    """Handle POST /api/fs/reveal — open a directory in the system file manager."""
    raw = (obj.get("path") or "").strip()
    if not raw:
        return handler._send_json({"ok": False, "error": "path is required"}, 400)
    try:
        resolved = Path(raw).expanduser().resolve()
    except OSError as e:
        return handler._send_json({"ok": False, "error": str(e)}, 400)
    if not _is_allowed_path(resolved):
        return handler._send_json({"ok": False, "error": "access denied"}, 403)
    if not resolved.is_dir():
        return handler._send_json({"ok": False, "error": "not a directory"}, 400)
    try:
        opened = reveal_path_in_file_manager(resolved)
    except OSError as e:
        return handler._send_json({"ok": False, "error": str(e)}, 500)
    return handler._send_json({"ok": True, "path": str(opened)})


def handle_get_fs_videos(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    """Handle GET /api/fs/videos — list video files in a directory."""
    dir_path = qs.get("path", [""])[0]
    if not dir_path:
        return handler._send_json({"error": "path is required"}, 400)
    try:
        resolved = Path(dir_path).resolve()
        if not _is_allowed_path(resolved):
            return handler._send_json({"error": "access denied"}, 403)
        if not resolved.is_dir():
            return handler._send_json({"error": "not a directory"}, 400)
        files: list[dict[str, Any]] = []
        try:
            with os.scandir(resolved) as it:
                for entry in it:
                    if entry.is_dir() or entry.name.startswith("."):
                        continue
                    ext = Path(entry.name).suffix.lower()
                    if ext not in VIDEO_EXTENSIONS:
                        continue
                    st = entry.stat()
                    files.append(
                        {
                            "name": entry.name,
                            "path": entry.path,
                            "size": st.st_size,
                        }
                    )
        except PermissionError:
            pass
        files.sort(key=lambda f: f["name"].lower())
        parent = str(resolved.parent) if resolved.parent != resolved else None
        return handler._send_json(
            {
                "path": str(resolved),
                "files": files,
                "parent": parent,
            }
        )
    except PermissionError:
        return handler._send_json({"error": "access denied"}, 403)
    except OSError as e:
        return handler._send_json({"error": str(e)}, 500)
