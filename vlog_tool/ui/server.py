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
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

from vlog_tool.config import AppConfig

STATIC_DIR = Path(__file__).parent / "static"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}

def _is_safe_basename(name: str) -> bool:
    if not name or len(name) > 200:
        return False
    if "/" in name or "\\" in name or ".." in name:
        return False
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
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


def _find_original_for_compressed(stem: str, input_dir: Path) -> str | None:
    """For a compressed stem like '001_GL010695', find the matching original basename
    in input_dir. Match is case-insensitive on the GoPro-style suffix (everything
    after the first '_'). Returns the original filename or None if not found.
    """
    if "_" not in stem or not input_dir.is_dir():
        return None
    suffix = stem.split("_", 1)[1].lower()
    for p in input_dir.iterdir():
        if p.is_file() and p.stem.lower() == suffix:
            return p.name
    return None


def _find_compressed_for_original(stem: str, comp_dir: Path) -> tuple[str, str] | None:
    """For an original stem like 'GL010695', find the matching compressed file and
    its index. Returns (compressed_basename, index) or None if not found.
    """
    if not comp_dir.is_dir():
        return None
    needle = stem.lower()
    for p in comp_dir.iterdir():
        if p.suffix.lower() not in VIDEO_EXTS or "_" not in p.stem:
            continue
        idx, rest = p.stem.split("_", 1)
        if rest.lower() == needle:
            return (p.name, idx)
    return None


def _coerce_config_types(new_val: Any, ref_val: Any) -> Any:
    if ref_val is None:
        return new_val
    if isinstance(ref_val, bool):
        if isinstance(new_val, str):
            return new_val.lower() in ("true", "1", "yes")
        return bool(new_val)
    if isinstance(ref_val, int):
        if new_val is None:
            return None
        try:
            return int(new_val)
        except (ValueError, TypeError):
            return new_val
    if isinstance(ref_val, float):
        if new_val is None:
            return None
        try:
            return float(new_val)
        except (ValueError, TypeError):
            return new_val
    if isinstance(ref_val, str):
        return str(new_val) if not isinstance(new_val, str) else new_val
    if isinstance(ref_val, list) and isinstance(new_val, list):
        if ref_val and new_val:
            return [_coerce_config_types(n, ref_val[0]) for n in new_val]
        return new_val
    if isinstance(ref_val, dict) and isinstance(new_val, dict):
        result = {}
        for k in ref_val:
            if k in new_val:
                result[k] = _coerce_config_types(new_val[k], ref_val[k])
        for k in new_val:
            if k not in result:
                result[k] = new_val[k]
        return result
    return new_val


def make_handler(config: AppConfig, config_path: Path | None = None) -> type[BaseHTTPRequestHandler]:
    output_dir = config.paths.output_dir
    input_dir = config.paths.input_dir
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
                    "input_dir": str(input_dir),
                    "output_dir": str(output_dir),
                    "compressed_dir": str(comp),
                    "texts_dirs": [str(d) for d in texts],
                    "scripts_dir": str(output_dir / "scripts"),
                    "plans_dir": str(output_dir / "plans"),
                })

            if path == "/api/config/raw":
                if not config_path or not config_path.is_file():
                    return self._send_json({"error": "config file not available"}, 500)
                with open(config_path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                return self._send_json(raw)

            if path == "/api/videos":
                source = qs.get("source", ["compressed"])[0]
                if source not in ("compressed", "original"):
                    return self._send_json(
                        {"ok": False, "error": "source must be compressed|original"}, 400
                    )
                comp_dir = output_dir / "compressed"
                # texts/scripts sidecars are keyed by the compressed index in both views
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
                videos: list[dict] = []
                if source == "compressed":
                    if comp_dir.is_dir():
                        for p in sorted(comp_dir.iterdir()):
                            if p.suffix.lower() not in VIDEO_EXTS:
                                continue
                            stem = p.stem
                            idx = stem.split("_", 1)[0] if "_" in stem else ""
                            orig = _find_original_for_compressed(stem, input_dir)
                            videos.append({
                                "file": p.name,
                                "source": "compressed",
                                "index": idx,
                                "text_json": (text_sidecars.get(idx) or [None])[0],
                                "script_json": (script_sidecars.get(idx) or [None])[0],
                                "match": ({"source": "original", "file": orig} if orig else None),
                            })
                else:  # original
                    if input_dir.is_dir():
                        for p in sorted(input_dir.iterdir()):
                            if p.suffix.lower() not in VIDEO_EXTS:
                                continue
                            comp = _find_compressed_for_original(p.stem, comp_dir)
                            idx = comp[1] if comp else None
                            videos.append({
                                "file": p.name,
                                "source": "original",
                                "index": idx,
                                "text_json": (text_sidecars.get(idx) or [None])[0] if idx else None,
                                "script_json": (script_sidecars.get(idx) or [None])[0] if idx else None,
                                "match": (
                                    {"source": "compressed", "file": comp[0], "index": comp[1]}
                                    if comp else None
                                ),
                            })
                return self._send_json({"videos": videos, "source": source})

            if path == "/api/video":
                fname = qs.get("file", [""])[0]
                source = qs.get("source", ["compressed"])[0]
                if not _is_safe_basename(fname):
                    return self.send_error(HTTPStatus.FORBIDDEN)
                if source == "original":
                    vp = input_dir / fname
                else:
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

            if path == "/api/config/raw":
                if not config_path:
                    return self._send_json({"ok": False, "error": "config_path not available"}, 500)
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        ref_raw = yaml.safe_load(f) or {}
                except Exception as e:
                    return self._send_json({"ok": False, "error": f"无法读取当前配置: {e}"}, 500)
                coerced = _coerce_config_types(obj, ref_raw)
                try:
                    yml = yaml.dump(coerced, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
                except Exception as e:
                    return self._send_json({"ok": False, "error": f"YAML 序列化失败: {e}"}, 400)
                tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".yaml", delete=False, dir=str(config_path.parent))
                try:
                    tmp.write(yml.encode("utf-8"))
                    tmp.close()
                    from vlog_tool.config import load_config
                    load_config(tmp.name)
                except (ValueError, FileNotFoundError, Exception) as e:
                    os.unlink(tmp.name)
                    return self._send_json({"ok": False, "error": f"配置校验失败: {e}"}, 400)
                _save_atomic(config_path, yml.encode("utf-8"))
                os.unlink(tmp.name)
                return self._send_json({"ok": True, "path": str(config_path)})

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
    config_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> int:
    handler = make_handler(config, config_path)
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
