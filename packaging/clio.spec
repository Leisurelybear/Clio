# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for the Clio desktop shell (R-032c).

Build:
    pip install pyinstaller pywebview
    pyinstaller packaging/clio.spec

Output: dist/clio/clio.exe (onedir).
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent.resolve()

a = Analysis(
    [str(ROOT / "clio" / "desktop" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "clio" / "ui" / "static"), "clio/ui/static"),
        (str(ROOT / "templates"), "templates"),
    ],
    hiddenimports=[
        # pywebview picks its Windows platform (winforms / WebView2) at runtime.
        "webview.platforms.winforms",
        "clr",
        "pythonnet",
        # Lazy `from tkinter import ...` inside dialogs.py / app.py.
        "tkinter",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "desktop_rthook.py")],
    excludes=[
        # Whisper is an optional feature installed on demand via `whisper install`
        # (a pip subprocess). Bundling its ML stack (torch + transformers +
        # ctranslate2 + tokenizers + PyAV) would balloon the onedir to ~4 GB.
        "faster_whisper",
        "ctranslate2",
        "torch",
        "torchvision",
        "torchaudio",
        "transformers",
        "tokenizers",
        "accelerate",
        "av",
        "soundfile",
        "nvidia",
        "triton",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="clio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="clio",
)
