# clio/desktop/dialogs.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from clio._constants import VIDEO_EXTENSIONS


def _askdirectory(**kwargs: Any) -> str:
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(**kwargs) or ""
    finally:
        root.destroy()


def _askopenfilename(**kwargs: Any) -> str:
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilename(**kwargs) or ""
    finally:
        root.destroy()


def _askopenfilenames(**kwargs: Any) -> tuple[str, ...] | list[str] | str:
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilenames(**kwargs) or ()
    finally:
        root.destroy()


def _video_filetypes(exts: list[str] | None = None) -> list[tuple[str, str]]:
    use = exts or sorted(e.lstrip(".").lower() for e in VIDEO_EXTENSIONS)
    pattern = " ".join(f"*.{e.lstrip('.')}" for e in use)
    return [("Videos", pattern), ("All files", "*.*")]


def _normalize_existing(path: str | None) -> str | None:
    if not path:
        return None
    return str(Path(path).expanduser().resolve())


def pick_folder(initial_dir: str | None = None) -> str | None:
    kwargs: dict[str, Any] = {}
    if initial_dir:
        kwargs["initialdir"] = initial_dir
    raw = _askdirectory(**kwargs)
    return _normalize_existing(raw) if raw else None


def pick_file(initial_dir: str | None = None, exts: list[str] | None = None) -> str | None:
    kwargs: dict[str, Any] = {"filetypes": _video_filetypes(exts)}
    if initial_dir:
        kwargs["initialdir"] = initial_dir
    raw = _askopenfilename(**kwargs)
    return _normalize_existing(raw) if raw else None


def pick_files(
    initial_dir: str | None = None,
    multiple: bool = True,
    exts: list[str] | None = None,
) -> list[str]:
    if not multiple:
        one = pick_file(initial_dir=initial_dir, exts=exts)
        return [one] if one else []
    kwargs: dict[str, Any] = {"filetypes": _video_filetypes(exts)}
    if initial_dir:
        kwargs["initialdir"] = initial_dir
    raw = _askopenfilenames(**kwargs)
    if not raw:
        return []
    if isinstance(raw, str):
        raw = (raw,)
    out: list[str] = []
    for p in raw:
        n = _normalize_existing(p)
        if n:
            out.append(n)
    return out


def envelope_path(path: str | None) -> dict[str, Any]:
    if not path:
        return {"ok": False, "cancelled": True}
    return {"ok": True, "path": path}


def envelope_paths(paths: list[str]) -> dict[str, Any]:
    if not paths:
        return {"ok": False, "cancelled": True}
    return {"ok": True, "paths": paths}


def envelope_error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": str(message)}
