# Clio Desktop — PyInstaller onedir build

Packages the desktop shell (`python -m clio.desktop`) as a standalone Windows
folder (onedir), no Python needed on the target machine.

## Requirements (build machine)

- Python 3.10+
- `pip install pyinstaller pywebview pythonnet`
- ffmpeg / ffprobe discoverable by the target machine (see below)

## Build

```powershell
# one-click
.\packaging\build-desktop.ps1

# or manual
python -m PyInstaller packaging/clio.spec --noconfirm --clean
```

Output: `dist/clio/clio.exe` (onedir — keep the whole `dist/clio` folder
together; do not move the exe alone).

Launch:

```powershell
.\dist\clio\clio.exe          # uses ./config.yaml in the current directory
.\dist\clio\clio.exe -c .\project\config.yaml
```

The app serves the UI on a random loopback port and opens a native window.
Closing the window stops the local server; closing during a run asks for
confirmation and sends a cancel request first.

## What is bundled

- `clio/**` Python package + `clio/ui/static` web UI assets
- `templates/` (trip_context.md, prompt overrides)
- pywebview WebView2 (EdgeChromium) engine via pythonnet

## Caveats

### WebView2 Evergreen runtime

The window is rendered by the **WebView2 Runtime** (Microsoft Edge Chromium).
Windows 11 ships it; Windows 10 needs the Evergreen runtime installed
<https://developer.microsoft.com/microsoft-edge/webview2/>. Without it the
window will fail to open.

### Unsigned exe — SmartScreen warning

The build is unsigned, so Windows SmartScreen shows "Windows protected your PC"
on first run. Workarounds:

- **More info → Run anyway** (per machine)
- Unblock once: `Unblock-File .\dist\clio\clio.exe`
- Ship a code-signing certificate for production

### ffmpeg / ffprobe

The app shells out to `ffmpeg` / `ffprobe` (compression, waveform, cutting).
These are **not** bundled — the target machine must have them on `PATH`, or
`config.yaml` `paths.ffmpeg` / `paths.ffprobe` must point at them. `setup.ps1`
installs them for dev machines.

### Whisper transcription is not bundled

`faster-whisper` (torch + transformers + ctranslate2 ≈ 4 GB) is excluded from
the bundle. Transcription still works when running from source
(`python main.py whisper install`); in the packaged app the transcription step
reports that whisper is unavailable.

### API keys

Keys are read from environment variables / `.env` next to `config.yaml`. Never
bake keys into the build.

## Measured cold-start (2026-08-01, Windows 10, x64)

- Onedir size: ~123 MB (excl. whisper ML stack)
- Exe launch → loopback HTTP ready → SPA index 200: **~2.1 s**
