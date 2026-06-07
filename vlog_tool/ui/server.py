"""本地 web UI: 视频 + 播放器 + JSON 文本可视化编辑。

- 零外部依赖: stdlib http.server
- 默认仅监听 127.0.0.1 (不暴露到局域网)
- 所有文件 IO 都沙盒在 config.paths.output_dir 内, 防止路径穿越
- 写入采用 atomic rename, 首次覆盖会自动留一份 .bak
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from vlog_tool.config import AppConfig

STATIC_DIR = Path(__file__).parent / "static"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}

# Basename 字符白名单: 字母数字 + 中文/unicode 词字符 + . _ - 和空格
SAFE_NAME = re.compile(r"^[\w\-. ]+$")


def _is_safe_basename(name: str) -> bool:
    if not name or len(name) > 200:
        return False
    if "/" in name or "\\" in name or ".." in name:
        return False
    if not SAFE_NAME.match(name):
        return False
    return True


def _find_texts_dirs(output_dir: Path) -> list[Path]:
    """返回所有 texts* 子目录 (texts, texts - 巴黎, ...)。"""
    if not output_dir.is_dir():
        return []
    return [d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("texts")]


def _save_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.with_suffix(path.suffix + ".bak").exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def make_handler(config: AppConfig) -> type[BaseHTTPRequestHandler]:
    output_dir = config.paths.output_dir
    static_dir = STATIC_DIR

    class Handler(BaseHTTPRequestHandler):
        # 把 server 端日志通过 print 输出, 走 _TeeWriter 同步进 logs/
        def log_message(self, fmt, *args):
            print(f"  [serve] {self.address_string()} - {fmt % args}")

        def _send_json(self, obj, status: int = 200) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, data: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_static(self, rel: str) -> None:
            target = (static_dir / rel).resolve()
            if not str(target).startswith(str(static_dir.resolve())):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            ct = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix == ".js":
                ct = "application/javascript; charset=utf-8"
            elif target.suffix == ".css":
                ct = "text/css; charset=utf-8"
            elif target.suffix == ".html":
                ct = "text/html; charset=utf-8"
            self._send_bytes(target.read_bytes(), ct)

        def _send_video_range(self, path: Path) -> None:
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            rng = self.headers.get("Range")
            if rng:
                m = re.match(r"bytes=(\d*)-(\d*)", rng)
                if not m:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                start_s, end_s = m.group(1), m.group(2)
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else size - 1
                if start >= size or end >= size or start > end:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
            else:
                start = 0
                length = size
                self.send_response(200)
                self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with path.open("rb") as f:
                f.seek(start)
                remaining = length
                chunk = 64 * 1024
                while remaining > 0:
                    buf = f.read(min(chunk, remaining))
                    if not buf:
                        break
                    self.wfile.write(buf)
                    remaining -= len(buf)

        def _resolve_texts(self, basename: str) -> Path | None:
            if not _is_safe_basename(basename):
                return None
            for d in _find_texts_dirs(output_dir):
                p = d / basename
                if p.is_file():
                    return p
            return None

        def _resolve_in(self, subdir: str, basename: str) -> Path | None:
            if not _is_safe_basename(basename):
                return None
            if subdir == "texts":
                return self._resolve_texts(basename)
            d = output_dir / subdir
            if not d.is_dir():
                return None
            p = d / basename
            return p if p.is_file() else None

        def do_GET(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path

            if path in ("/", "/index.html"):
                return self._send_static("index.html")
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                if ".." in rel or rel.startswith("/"):
                    return self.send_error(HTTPStatus.FORBIDDEN)
                return self._send_static(rel)

            if path == "/api/config":
                comp = output_dir / "compressed"
                texts = _find_texts_dirs(output_dir)
                return self._send_json({
                    "output_dir": str(output_dir),
                    "compressed_dir": str(comp),
                    "texts_dirs": [str(d) for d in texts],
                    "scripts_dir": str(output_dir / "scripts"),
                    "plans_dir": str(output_dir / "plans"),
                })

            if path == "/api/videos":
                comp_dir = output_dir / "compressed"
                videos: list[dict] = []
                if comp_dir.is_dir():
                    # 先把所有 texts* 下的 sidecar JSON 索引: index -> [basename, ...]
                    text_sidecars: dict[str, list[str]] = {}
                    for td in _find_texts_dirs(output_dir):
                        for f in td.iterdir():
                            if f.suffix != ".json" or "_" not in f.stem:
                                continue
                            idx = f.stem.split("_", 1)[0]
                            text_sidecars.setdefault(idx, []).append(f.name)
                    script_sidecars: dict[str, list[str]] = {}
                    sd = output_dir / "scripts"
                    if sd.is_dir():
                        for f in sd.iterdir():
                            if f.suffix != ".json" or "_" not in f.stem:
                                continue
                            idx = f.stem.split("_", 1)[0]
                            script_sidecars.setdefault(idx, []).append(f.name)
                    for p in sorted(comp_dir.iterdir()):
                        if p.suffix.lower() not in VIDEO_EXTS:
                            continue
                        stem = p.stem
                        idx = stem.split("_", 1)[0] if "_" in stem else ""
                        videos.append({
                            "file": p.name,
                            "index": idx,
                            "text_json": (text_sidecars.get(idx) or [None])[0],
                            "script_json": (script_sidecars.get(idx) or [None])[0],
                        })
                return self._send_json({"videos": videos})

            if path == "/api/video":
                fname = qs.get("file", [""])[0]
                if not _is_safe_basename(fname):
                    return self.send_error(HTTPStatus.FORBIDDEN)
                vp = output_dir / "compressed" / fname
                if not vp.is_file() or vp.suffix.lower() not in VIDEO_EXTS:
                    return self.send_error(HTTPStatus.NOT_FOUND)
                return self._send_video_range(vp)

            if path == "/api/texts":
                fname = qs.get("file", [""])[0]
                p = self._resolve_texts(fname)
                if p is None:
                    return self.send_error(HTTPStatus.NOT_FOUND)
                return self._send_bytes(p.read_bytes(), "application/json; charset=utf-8")

            if path == "/api/voiceover":
                fname = qs.get("file", [""])[0]
                p = self._resolve_in("scripts", fname)
                if p is None:
                    return self.send_error(HTTPStatus.NOT_FOUND)
                return self._send_bytes(p.read_bytes(), "application/json; charset=utf-8")

            if path == "/api/plan":
                day = qs.get("day", [""])[0]
                if not _is_safe_basename(day) or not day:
                    return self.send_error(HTTPStatus.FORBIDDEN)
                p = output_dir / "plans" / f"{day}_plan.json"
                if not p.is_file():
                    return self.send_error(HTTPStatus.NOT_FOUND)
                return self._send_bytes(p.read_bytes(), "application/json; charset=utf-8")

            return self.send_error(HTTPStatus.NOT_FOUND)

        def do_PUT(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                obj = json.loads(raw.decode("utf-8"))
                if not isinstance(obj, dict):
                    raise ValueError("expected a JSON object")
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                return self._send_json({"ok": False, "error": f"invalid JSON: {e}"}, 400)

            if path == "/api/texts":
                fname = qs.get("file", [""])[0]
                p = self._resolve_texts(fname)
                if p is None:
                    return self._send_json({"ok": False, "error": "forbidden or not found"}, 403)
                data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
                _save_atomic(p, data)
                return self._send_json({"ok": True, "path": str(p)})

            if path == "/api/voiceover":
                fname = qs.get("file", [""])[0]
                p = self._resolve_in("scripts", fname)
                if p is None:
                    return self._send_json({"ok": False, "error": "forbidden or not found"}, 403)
                data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
                _save_atomic(p, data)
                return self._send_json({"ok": True, "path": str(p)})

            if path == "/api/plan":
                day = qs.get("day", [""])[0]
                if not _is_safe_basename(day) or not day:
                    return self._send_json({"ok": False, "error": "forbidden"}, 403)
                p = output_dir / "plans" / f"{day}_plan.json"
                data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
                _save_atomic(p, data)
                return self._send_json({"ok": True, "path": str(p)})

            return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    return Handler


def run(
    config: AppConfig,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> int:
    handler = make_handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"  UI 启动: {url}")
    print(f"  output_dir: {config.paths.output_dir}")
    print("  Ctrl+C 退出")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  UI 关闭")
    finally:
        server.server_close()
    return 0
