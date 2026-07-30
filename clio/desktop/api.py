# clio/desktop/api.py
"""js_api surface for the pywebview desktop shell.

Thread decision: tkinter dialogs are invoked on the pywebview js_api worker
thread (not the UI main thread). If pick_* hangs under pywebview on Windows,
switch dialogs.py to Win32 IFileOpenDialog (COM) while keeping these method names.
"""

from __future__ import annotations

from pathlib import Path

from clio.desktop import dialogs
from clio.desktop.state import resolve_initial_dir, save_last_dir


class DesktopApi:
    def __init__(self, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)

    def _initial(self, initial_dir: str = "") -> str | None:
        return resolve_initial_dir(self._config_dir, initial_dir or None)

    def pick_folder(self, initial_dir: str = "") -> dict:
        try:
            path = dialogs.pick_folder(self._initial(initial_dir))
            if path:
                save_last_dir(self._config_dir, path, is_file=False)
            return dialogs.envelope_path(path)
        except Exception as e:  # noqa: BLE001 — surface to JS
            return dialogs.envelope_error(str(e))

    def pick_file(self, initial_dir: str = "", kind: str = "video") -> dict:
        try:
            exts = _exts_for_kind(kind)
            path = dialogs.pick_file(self._initial(initial_dir), exts=exts)
            if path:
                save_last_dir(self._config_dir, path, is_file=True)
            return dialogs.envelope_path(path)
        except Exception as e:  # noqa: BLE001
            return dialogs.envelope_error(str(e))

    def pick_files(self, initial_dir: str = "", kind: str = "video") -> dict:
        try:
            exts = _exts_for_kind(kind)
            paths = dialogs.pick_files(self._initial(initial_dir), multiple=True, exts=exts)
            if paths:
                save_last_dir(self._config_dir, paths[0], is_file=True)
            return dialogs.envelope_paths(paths)
        except Exception as e:  # noqa: BLE001
            return dialogs.envelope_error(str(e))


def _exts_for_kind(kind: str) -> list[str] | None:
    if kind == "exe":
        return ["exe"]
    if kind == "any":
        # Empty list → dialogs._video_filetypes returns all-files only.
        return []
    return None  # default video set inside dialogs
