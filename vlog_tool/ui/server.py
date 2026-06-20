"""Local web UI: video + player + JSON text visualization editing.

- Zero external dependencies: stdlib http.server
- Defaults to 127.0.0.1 only (not exposed to LAN)
- All file IO sandboxed within config.paths.output_dir to prevent path traversal
- Writes use atomic rename, first overwrite leaves a .bak copy
"""

from __future__ import annotations

import copy
import json
import mimetypes
import re
import shutil
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from vlog_tool.config import AppConfig, load_config
from vlog_tool.session_log import clear as clear_session_log
from vlog_tool.session_log import read as read_session_log
from vlog_tool.ui.routes.config_routes import (
    handle_get_config,
    handle_get_config_raw,
    handle_post_config_init,
    handle_put_config_raw,
)
from vlog_tool.ui.routes.env_routes import handle_get_env, handle_put_env
from vlog_tool.ui.routes.fs import handle_get_fs_dirs
from vlog_tool.ui.routes.plan import (
    handle_get_plan,
    handle_get_plans,
    handle_post_cut,
    handle_put_plan,
)
from vlog_tool.ui.routes.processing_state_routes import handle_get_processing_state
from vlog_tool.ui.routes.projects import (
    handle_get_project,
    handle_get_projects,
    handle_post_project_add,
    handle_post_project_create,
    handle_post_project_remove,
    handle_put_project,
)
from vlog_tool.ui.routes.run import (
    handle_get_run_status,
    handle_post_rerun,
    handle_post_run_cancel,
    handle_post_run_start,
)
from vlog_tool.ui.routes.static_files import handle_favicon, handle_index, handle_static
from vlog_tool.ui.routes.texts import (
    handle_get_texts,
    handle_get_voiceover,
    handle_put_texts,
    handle_put_voiceover,
)
from vlog_tool.ui.routes.transcripts import (
    handle_get_transcripts,
    handle_put_transcripts,
)
from vlog_tool.ui.routes.videos import handle_get_video, handle_get_videos
from vlog_tool.ui.routes.whisper_routes import (
    handle_get_whisper_check,
    handle_get_whisper_install_status,
    handle_get_whisper_models,
    handle_post_whisper_install,
    handle_post_whisper_model_delete,
    handle_put_whisper_model,
)
from vlog_tool.ui.services.file_service import _find_texts_dirs, _is_safe_basename
from vlog_tool.ui.services.project_service import _project_output_dir, _registry_path
from vlog_tool.utils import write_json_atomic

STATIC_DIR = Path(__file__).parent / "static"


def make_handler(config: AppConfig, config_path: Path | None = None) -> type[BaseHTTPRequestHandler]:
    output_dir = config.paths.output_dir
    input_dir = config.paths.input_dir
    static_dir = STATIC_DIR
    project_path = input_dir / "project.json"

    # Compatibility: migrate old location project.json
    old_project_path = output_dir / "project.json"
    if not project_path.is_file() and old_project_path.is_file():
        try:
            shutil.copy2(old_project_path, project_path)
        except OSError:
            pass
    # Fix name after migration
    if project_path.is_file():
        try:
            cur = json.loads(project_path.read_text(encoding="utf-8"))
            if cur.get("name") == output_dir.name and input_dir.name != output_dir.name:
                cur["name"] = input_dir.name
                write_json_atomic(project_path, cur)
        except (json.JSONDecodeError, OSError):
            pass

    DEFAULT_PROJECT = {
        "currentDay": "day1",
        "source": "compressed",
        "name": input_dir.name,
        "output_dir": str(output_dir.resolve()),
        "lastEntity": None,
        "lastVideo": None,
    }

    class Handler(BaseHTTPRequestHandler):
        # Shared state (class-level, across instances)
        _run_lock = threading.Lock()
        _run_thread: threading.Thread | None = None
        _cancel_event = threading.Event()
        _config_cache: dict[str, AppConfig] = {}
        _config_meta: dict[str, tuple[float | None, float | None]] = {}
        _config_cache_lock = threading.Lock()
        DEFAULT_PROJECT: dict = {}
        server: Any  # set by HTTPServer

        def _get_config(self, project_input: Path | None = None) -> AppConfig:
            """Return project-specific config (deep-merged with project.yaml), cached.

            Cache is LRU-style: capped at 20 entries, evicts oldest when full.
            On each access, checks config file mtime to detect external edits.
            """
            _GLOBAL_KEY = "__global__"
            key = _GLOBAL_KEY if project_input is None else str(project_input.resolve())

            # Read current mtimes
            if config_path is None:
                cfg_mtime = 0.0
            else:
                try:
                    cfg_mtime = config_path.stat().st_mtime
                except OSError:
                    cfg_mtime = 0.0
            project_yaml = None if project_input is None else (project_input / "project.yaml")
            try:
                proj_mtime = project_yaml.stat().st_mtime if project_yaml else 0.0
            except OSError:
                proj_mtime = 0.0

            with self.__class__._config_cache_lock:
                cache = self.__class__._config_cache
                meta = self.__class__._config_meta

                if key in cache:
                    old_cfg_mtime, old_proj_mtime = meta.get(key, (0, 0))
                    if cfg_mtime == old_cfg_mtime and proj_mtime == old_proj_mtime:
                        return copy.deepcopy(cache[key])
                    # Stale — evict and reload
                    del cache[key]
                    meta.pop(key, None)

                # Load fresh config
                new_config = load_config(config_path, project_dir=project_input)

                # LRU eviction if at capacity
                if len(cache) >= 20:
                    oldest_key = next(iter(cache))
                    cache.pop(oldest_key)
                    meta.pop(oldest_key, None)

                cache[key] = new_config
                meta[key] = (cfg_mtime, proj_mtime)
                return copy.deepcopy(new_config)

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

        def _resolve_project_input(self, qs: dict) -> Path:
            """Resolve project input directory from query params; default to current input_dir.

            Priority:
              1. input_dir query param (direct path, unambiguous)
              2. project name query param (may be ambiguous)
            """
            # Direct input_dir param takes priority
            input_dir_raw = qs.get("input_dir", [None])[0]
            if input_dir_raw:
                candidate = Path(input_dir_raw)
                if candidate.is_dir():
                    return candidate
                # Invalid path — fall through to name-based

            project_name = qs.get("project", [None])[0]
            if not project_name:
                return input_dir

            candidates: list[Path] = []
            seen: set[str] = set()

            def _read_name(p: Path) -> str | None:
                proj_file = p / "project.json"
                if not proj_file.is_file():
                    return None
                try:
                    data = json.loads(proj_file.read_text(encoding="utf-8"))
                    return data.get("name")
                except (json.JSONDecodeError, OSError):
                    return None

            def _score(p: Path) -> int:
                s = 0
                if p.name == project_name:
                    s += 10
                if p.resolve() == input_dir.resolve():
                    s += 5
                return s

            # 1. Registry first (user-added order)
            registry_file = _registry_path(config_path)
            if registry_file.is_file():
                try:
                    reg = json.loads(registry_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    reg = {}
                for p_str in reg.get("projects", []):
                    p = Path(p_str)
                    resolved = str(p.resolve())
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    name = _read_name(p)
                    if name == project_name:
                        candidates.append(p)

            # 2. Sibling directories (auto-discovery)
            projects_root = input_dir.parent
            if projects_root.is_dir():
                for p in sorted(projects_root.iterdir()):
                    if not p.is_dir():
                        continue
                    resolved = str(p.resolve())
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    name = _read_name(p)
                    if name == project_name:
                        candidates.append(p)

            if not candidates:
                return input_dir
            if len(candidates) == 1:
                return candidates[0]
            candidates.sort(key=_score, reverse=True)
            return candidates[0]

        def _get_project_output(self, qs_or_proj_dir: dict | Path) -> Path:
            """Return output_dir for a project. Accepts qs dict or resolved input_dir Path."""
            if isinstance(qs_or_proj_dir, dict):
                proj_input = self._resolve_project_input(qs_or_proj_dir)
            else:
                proj_input = qs_or_proj_dir
            return _project_output_dir(proj_input)

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
                if start_s == "" and end_s != "":
                    suffix_len = int(end_s)
                    start = max(0, size - suffix_len)
                    end = size - 1
                else:
                    start = int(start_s) if start_s else 0
                    end = int(end_s) if end_s else size - 1
                if start >= size or end >= size or start > end:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                length = end - start + 1
                if length <= 0:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
            else:
                start = 0
                length = size
                self.send_response(200)
                self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            _VIDEO_MIME = {
                ".mp4": "video/mp4",
                ".mov": "video/quicktime",
                ".webm": "video/webm",
                ".m4v": "video/x-m4v",
                ".lrv": "video/mp4",
            }
            self.send_header("Content-Type", _VIDEO_MIME.get(path.suffix.lower(), "video/mp4"))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with path.open("rb") as f:
                f.seek(start)
                remaining = length
                chunk = 64 * 1024
                try:
                    while remaining > 0:
                        buf = f.read(min(chunk, remaining))
                        if not buf:
                            break
                        self.wfile.write(buf)
                        remaining -= len(buf)
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                    pass

        def _resolve_texts(self, basename: str, proj_out: Path | None = None) -> Path | None:
            if not _is_safe_basename(basename):
                return None
            base = proj_out or output_dir
            for d in _find_texts_dirs(base):
                p = d / basename
                if p.is_file():
                    return p
            return None

        def _resolve_in(self, subdir: str, basename: str, proj_out: Path | None = None) -> Path | None:
            if not _is_safe_basename(basename):
                return None
            if subdir == "texts":
                return self._resolve_texts(basename, proj_out)
            base = proj_out or output_dir
            d = base / subdir
            if not d.is_dir():
                return None
            p = d / basename
            return p if p.is_file() else None

        # ---- HTTP method dispatchers ----

        def do_GET(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path

            if path in ("/", "/index.html"):
                return handle_index(self)
            if path == "/favicon.ico":
                return handle_favicon(self)
            if path.startswith("/static/"):
                rel = path[len("/static/") :]
                return handle_static(self, rel)

            if path == "/api/config":
                return handle_get_config(self, qs)
            if path == "/api/config/raw":
                return handle_get_config_raw(self, qs)
            if path == "/api/project":
                return handle_get_project(self, qs)
            if path == "/api/projects":
                return handle_get_projects(self, qs)
            if path == "/api/videos":
                return handle_get_videos(self, qs)
            if path == "/api/video":
                return handle_get_video(self, qs)
            if path == "/api/texts":
                return handle_get_texts(self, qs)
            if path == "/api/voiceover":
                return handle_get_voiceover(self, qs)
            if path == "/api/plans":
                return handle_get_plans(self, qs)
            if path == "/api/run/status":
                return handle_get_run_status(self, qs)
            if path == "/api/plan":
                return handle_get_plan(self, qs)
            if path == "/api/processing-state":
                return handle_get_processing_state(self, qs)
            if path == "/api/fs/dirs":
                return handle_get_fs_dirs(self, qs)
            if path == "/api/transcripts":
                return handle_get_transcripts(self, qs)
            if path == "/api/whisper/check":
                return handle_get_whisper_check(self)
            if path == "/api/whisper/install/status":
                return handle_get_whisper_install_status(self)
            if path == "/api/whisper/models":
                return handle_get_whisper_models(self)
            if path == "/api/env":
                return handle_get_env(self, qs)
            if path == "/api/logs":
                offset = int(qs.get("offset", ["0"])[0])
                return self._send_json(read_session_log(offset))

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
                return handle_put_config_raw(self, qs, obj)
            if path == "/api/project":
                return handle_put_project(self, qs, obj)
            if path == "/api/texts":
                return handle_put_texts(self, qs, obj)
            if path == "/api/voiceover":
                return handle_put_voiceover(self, qs, obj)
            if path == "/api/plan":
                return handle_put_plan(self, qs, obj)
            if path == "/api/transcripts":
                return handle_put_transcripts(self, qs, obj)
            if path == "/api/whisper/model":
                return handle_put_whisper_model(self, qs, obj)
            if path == "/api/env":
                return handle_put_env(self, qs, obj)

            return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

        def do_POST(self):
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

            if path == "/api/run/start":
                return handle_post_run_start(self, qs, obj)
            if path == "/api/run/cancel":
                return handle_post_run_cancel(self, qs, obj)
            if path == "/api/config/init":
                return handle_post_config_init(self, qs, obj)
            if path == "/api/cut":
                return handle_post_cut(self, qs, obj)
            if path == "/api/project/create":
                return handle_post_project_create(self, obj)
            if path == "/api/project/add":
                return handle_post_project_add(self, obj)
            if path == "/api/project/remove":
                return handle_post_project_remove(self, obj)
            if path == "/api/rerun":
                return handle_post_rerun(self, qs, obj)
            if path == "/api/whisper/install":
                return handle_post_whisper_install(self)
            if path == "/api/whisper/models/delete":
                return handle_post_whisper_model_delete(self, qs, obj)
            if path == "/api/logs/clear":
                clear_session_log()
                return self._send_json({"ok": True})

            return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    # Expose closure variables as class attrs so route modules can access them
    Handler.DEFAULT_PROJECT = DEFAULT_PROJECT
    Handler.input_dir = input_dir
    Handler.output_dir = output_dir
    Handler.config_path = config_path
    return Handler


def _resolve_last_project_config(config: AppConfig, config_path: Path | None) -> AppConfig:
    """If registry has a last_project, attempt to load its config instead of default.

    Supports both legacy (string name) and new (dict with name+input_dir) formats.
    """
    if not config_path:
        return config
    reg_file = config_path.parent / "projects.json"
    if not reg_file.is_file():
        return config
    try:
        reg = json.loads(reg_file.read_text(encoding="utf-8"))
        last_project = reg.get("last_project")
        if not last_project:
            return config

        # New format: dict with input_dir — resolve directly
        if isinstance(last_project, dict):
            input_dir_raw = last_project.get("input_dir")
            if input_dir_raw:
                p = Path(input_dir_raw)
                if p.is_dir():
                    cfg = load_config(config_path, project_dir=p)
                    return cfg

        # Legacy format: string name — match by project.json name
        last_name = last_project.get("name") if isinstance(last_project, dict) else last_project
        if not last_name:
            return config
        for p_str in reg.get("projects", []):
            p = Path(p_str)
            proj_file = p / "project.json"
            if not proj_file.is_file():
                continue
            data = json.loads(proj_file.read_text(encoding="utf-8"))
            if data.get("name") == last_name:
                cfg = load_config(config_path, project_dir=p)
                return cfg
        return config
    except Exception:
        return config


def run(
    config: AppConfig,
    config_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> int:
    # Try loading last used project config
    active_config = _resolve_last_project_config(config, config_path)
    handler = make_handler(active_config, config_path)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"  UI started: {url}")
    print(f"  Project directory: {active_config.paths.input_dir}")
    print(f"  Output directory: {active_config.paths.output_dir}")
    print("  Ctrl+C to exit")
    if open_browser:
        threading.Timer(0.5, lambda: _open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  UI closed")
    finally:
        server.server_close()
    return 0


def _open_browser(url: str) -> None:
    import webbrowser

    webbrowser.open(url)
