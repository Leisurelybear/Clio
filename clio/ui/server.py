"""Local web UI: video + player + JSON text visualization editing.

- Zero external dependencies: stdlib http.server
- Defaults to 127.0.0.1 only (not exposed to LAN)
- All file IO sandboxed within config.paths.output_dir to prevent path traversal
- Writes use atomic rename, first overwrite leaves a .bak copy
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

from clio.config import AppConfig
from clio.session_log import clear as clear_session_log
from clio.session_log import read as read_session_log
from clio.shutdown import before_stop, install_hooks
from clio.tasks.reindex import auto_reindex_if_needed
from clio.ui.routes.ai import handle_post_ai_test
from clio.ui.routes.config_routes import (
    handle_delete_provider,
    handle_get_config,
    handle_get_config_global,
    handle_get_config_project,
    handle_get_config_raw,
    handle_get_providers,
    handle_post_config_init,
    handle_post_provider,
    handle_put_config_global,
    handle_put_config_project,
    handle_put_config_raw,
    handle_put_provider,
)
from clio.ui.routes.env_routes import handle_get_env, handle_put_env
from clio.ui.routes.export import handle_post_export
from clio.ui.routes.fs import handle_get_fs_dirs
from clio.ui.routes.plan import (
    handle_get_plan,
    handle_get_plans,
    handle_post_cut,
    handle_put_plan,
)
from clio.ui.routes.processing_state_routes import handle_get_processing_state
from clio.ui.routes.projects import (
    handle_get_project,
    handle_get_projects,
    handle_post_project_add,
    handle_post_project_create,
    handle_post_project_remove,
    handle_put_project,
)
from clio.ui.routes.prompts import handle_delete_prompt, handle_get_prompts, handle_put_prompt
from clio.ui.routes.refine import handle_post_refine
from clio.ui.routes.run import (
    handle_get_run_status,
    handle_get_run_stream,
    handle_post_rerun,
    handle_post_run_cancel,
    handle_post_run_preview,
    handle_post_run_start,
)
from clio.ui.routes.static_files import handle_favicon, handle_index, handle_static
from clio.ui.routes.texts import (
    handle_get_texts,
    handle_get_voiceover,
    handle_put_texts,
    handle_put_voiceover,
)
from clio.ui.routes.token_routes import handle_get_token_usage
from clio.ui.routes.transcripts import (
    handle_get_transcripts,
    handle_post_transcripts,
    handle_put_transcripts,
)
from clio.ui.routes.videos import handle_get_video, handle_get_videos, handle_get_vmeta
from clio.ui.routes.whisper_routes import (
    handle_get_whisper_check,
    handle_get_whisper_install_status,
    handle_get_whisper_models,
    handle_post_whisper_install,
    handle_post_whisper_install_cancel,
    handle_post_whisper_model_delete,
    handle_put_whisper_model,
)
from clio.ui.services.config_cache import ConfigCache
from clio.ui.services.file_service import (
    resolve_in,
    resolve_texts,
    send_video_range,
)
from clio.ui.services.project_service import (
    _project_output_dir,
    resolve_last_project_config,
    resolve_project_input,
)
from clio.utils import write_json_atomic

STATIC_DIR = Path(__file__).parent / "static"


@dataclass(frozen=True)
class RoutePolicy:
    method: str
    path: str
    auth_required: bool = True
    prefix: bool = False


_ROUTE_POLICIES = (
    RoutePolicy("GET", "/", auth_required=False),
    RoutePolicy("GET", "/index.html", auth_required=False),
    RoutePolicy("GET", "/favicon.ico", auth_required=False),
    RoutePolicy("GET", "/static/", auth_required=False, prefix=True),
    RoutePolicy("GET", "/api/config"),
    RoutePolicy("GET", "/api/config/raw"),
    RoutePolicy("GET", "/api/config/global"),
    RoutePolicy("GET", "/api/config/project"),
    RoutePolicy("GET", "/api/project"),
    RoutePolicy("GET", "/api/projects"),
    RoutePolicy("GET", "/api/videos"),
    RoutePolicy("GET", "/api/video"),
    RoutePolicy("GET", "/api/vmeta/", prefix=True),
    RoutePolicy("GET", "/api/texts"),
    RoutePolicy("GET", "/api/voiceover"),
    RoutePolicy("GET", "/api/plans"),
    RoutePolicy("GET", "/api/plan"),
    RoutePolicy("GET", "/api/processing-state"),
    RoutePolicy("GET", "/api/run/status"),
    RoutePolicy("GET", "/api/run/stream"),
    RoutePolicy("GET", "/api/fs/dirs"),
    RoutePolicy("GET", "/api/transcripts"),
    RoutePolicy("GET", "/api/whisper/check"),
    RoutePolicy("GET", "/api/whisper/install/status"),
    RoutePolicy("GET", "/api/whisper/models"),
    RoutePolicy("GET", "/api/token-usage"),
    RoutePolicy("GET", "/api/env"),
    RoutePolicy("GET", "/api/logs"),
    RoutePolicy("PUT", "/api/config/raw"),
    RoutePolicy("PUT", "/api/config/global"),
    RoutePolicy("PUT", "/api/config/project"),
    RoutePolicy("PUT", "/api/project"),
    RoutePolicy("PUT", "/api/texts"),
    RoutePolicy("PUT", "/api/voiceover"),
    RoutePolicy("PUT", "/api/plan"),
    RoutePolicy("PUT", "/api/transcripts"),
    RoutePolicy("PUT", "/api/whisper/model"),
    RoutePolicy("PUT", "/api/env"),
    RoutePolicy("POST", "/api/run/start"),
    RoutePolicy("POST", "/api/run/preview"),
    RoutePolicy("POST", "/api/run/cancel"),
    RoutePolicy("POST", "/api/ai/test"),
    RoutePolicy("POST", "/api/config/init"),
    RoutePolicy("POST", "/api/cut"),
    RoutePolicy("POST", "/api/refine"),
    RoutePolicy("POST", "/api/export"),
    RoutePolicy("POST", "/api/project/create"),
    RoutePolicy("POST", "/api/project/add"),
    RoutePolicy("POST", "/api/project/remove"),
    RoutePolicy("POST", "/api/rerun"),
    RoutePolicy("POST", "/api/transcripts"),
    RoutePolicy("POST", "/api/whisper/install"),
    RoutePolicy("POST", "/api/whisper/install/cancel"),
    RoutePolicy("POST", "/api/whisper/models/delete"),
    RoutePolicy("POST", "/api/logs/clear"),
)
_ROUTE_POLICY_BY_METHOD_PATH = {(policy.method, policy.path): policy for policy in _ROUTE_POLICIES if not policy.prefix}
_ROUTE_PREFIX_POLICIES = tuple(policy for policy in _ROUTE_POLICIES if policy.prefix)


def _get_route_policy(method: str, path: str) -> RoutePolicy:
    method = method.upper()
    exact = _ROUTE_POLICY_BY_METHOD_PATH.get((method, path))
    if exact is not None:
        return exact
    for policy in _ROUTE_PREFIX_POLICIES:
        if policy.method == method and path.startswith(policy.path):
            return policy
    if path.startswith("/api/"):
        return RoutePolicy(method, path, auth_required=True)
    return RoutePolicy(method, path, auth_required=method in {"PUT", "POST"})


def _get_requires_auth(path: str, method: str = "GET") -> bool:
    return _get_route_policy(method, path).auth_required


@dataclass
class _ServerState:
    run_lock: threading.Lock = field(default_factory=threading.Lock)
    run_thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


def make_handler(
    config: AppConfig, config_path: Path | None = None, api_token: str = ""
) -> type[BaseHTTPRequestHandler]:
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

    # isort: split
    from clio.ui.handler_protocol import HandlerProtocol

    class Handler(BaseHTTPRequestHandler, HandlerProtocol):
        _project_states: dict[str, _ServerState]
        _config_cache: ClassVar[ConfigCache]
        DEFAULT_PROJECT: dict[str, Any] = {}
        input_dir: Path
        output_dir: Path
        config_path: Path | None
        _api_token: str | None

        def _get_state(self, project_key: str) -> _ServerState:
            states = self.__class__._project_states
            if project_key not in states:
                states[project_key] = _ServerState()
            return states[project_key]  # set by HTTPServer

        def log_message(self, fmt, *args):
            print(f"  [serve] {self.address_string()} - {fmt % args}")

        def _require_auth(self) -> bool:
            """Check Authorization header or ?token= query param against configured token.

            Returns True if authorized, sends 401 and returns False otherwise.
            If token is empty string, auth is disabled.
            """
            token = self.__class__._api_token
            if not token:
                return True
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and auth[7:] == token:
                return True
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            if qs.get("token", [None])[0] == token:
                return True
            self._send_json({"error": "未授权访问，需要有效的 API Token"}, 401)
            return False

        def _send_json(self, obj, status: int = 200) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, data: bytes, content_type: str = "application/octet-stream") -> None:
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

        def _get_config(self, project_input: Path | None = None) -> AppConfig:
            return self.__class__._config_cache.get(project_input)

        def _resolve_project_input(self, qs: dict) -> Path:
            return resolve_project_input(qs, input_dir, config_path)

        def _get_project_output(self, qs_or_proj_dir: dict | Path) -> Path:
            if isinstance(qs_or_proj_dir, dict):
                proj_input = self._resolve_project_input(qs_or_proj_dir)
            else:
                proj_input = qs_or_proj_dir
            return _project_output_dir(proj_input)

        def _send_video_range(self, path: Path) -> None:
            send_video_range(self, path)

        def _resolve_texts(self, basename: str, proj_out: Path | None = None) -> Path | None:
            return resolve_texts(basename, proj_out, output_dir)

        def _resolve_in(self, subdir: str, basename: str, proj_out: Path | None = None) -> Path | None:
            return resolve_in(subdir, basename, proj_out, output_dir)

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

            if _get_requires_auth(path, "GET") and not self._require_auth():
                return

            if path == "/api/config":
                return handle_get_config(self, qs)
            if path == "/api/config/raw":
                return handle_get_config_raw(self, qs)
            if path == "/api/config/global":
                return handle_get_config_global(self, qs)
            if path == "/api/config/project":
                return handle_get_config_project(self, qs)
            if path == "/api/providers":
                return handle_get_providers(self, qs)
            if path == "/api/project":
                return handle_get_project(self, qs)
            if path == "/api/projects":
                return handle_get_projects(self, qs)
            if path == "/api/videos":
                return handle_get_videos(self, qs)
            if path == "/api/video":
                return handle_get_video(self, qs)
            if path.startswith("/api/vmeta/"):
                stem = path[len("/api/vmeta/") :]
                return handle_get_vmeta(self, qs, stem)
            if path == "/api/texts":
                return handle_get_texts(self, qs)
            if path == "/api/voiceover":
                return handle_get_voiceover(self, qs)
            if path == "/api/plans":
                return handle_get_plans(self, qs)
            if path == "/api/run/status":
                return handle_get_run_status(self, qs)
            if path == "/api/run/stream":
                return handle_get_run_stream(self, qs)
            if path == "/api/plan":
                return handle_get_plan(self, qs)
            if path == "/api/processing-state":
                return handle_get_processing_state(self, qs)
            if path == "/api/fs/dirs":
                return handle_get_fs_dirs(self, qs)
            if path == "/api/transcripts":
                return handle_get_transcripts(self, qs)
            if path == "/api/whisper/check":
                return handle_get_whisper_check(self, qs)
            if path == "/api/whisper/install/status":
                return handle_get_whisper_install_status(self, qs)
            if path == "/api/whisper/models":
                return handle_get_whisper_models(self, qs)
            if path == "/api/token-usage":
                return handle_get_token_usage(self, qs)
            if path == "/api/env":
                return handle_get_env(self, qs)
            if path == "/api/prompts":
                return handle_get_prompts(self, qs)
            if path == "/api/logs":
                offset = int(qs.get("offset", ["0"])[0])
                return self._send_json(read_session_log(offset))

            return self.send_error(HTTPStatus.NOT_FOUND)

        def do_PUT(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path
            if _get_requires_auth(path, "PUT") and not self._require_auth():
                return
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
            if path == "/api/config/global":
                return handle_put_config_global(self, qs, obj)
            if path == "/api/config/project":
                return handle_put_config_project(self, qs, obj)
            if path.startswith("/api/providers/"):
                name = path[len("/api/providers/") :]
                return handle_put_provider(self, qs, obj, name)
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
            if path.startswith("/api/prompts/"):
                name = path[len("/api/prompts/") :]
                return handle_put_prompt(self, qs, obj, name)

            return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

        def do_POST(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path
            if _get_requires_auth(path, "POST") and not self._require_auth():
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                obj = json.loads(raw.decode("utf-8"))
                if not isinstance(obj, dict):
                    raise ValueError("expected a JSON object")
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                return self._send_json({"ok": False, "error": f"invalid JSON: {e}"}, 400)

            if path in {"/api/run/start", "/api/webhook/trigger"}:
                return handle_post_run_start(self, qs, obj)
            if path == "/api/run/preview":
                return handle_post_run_preview(self, qs, obj)
            if path == "/api/run/cancel":
                return handle_post_run_cancel(self, qs, obj)
            if path == "/api/ai/test":
                return handle_post_ai_test(self, qs, obj)
            if path == "/api/config/init":
                return handle_post_config_init(self, qs, obj)
            if path == "/api/providers":
                return handle_post_provider(self, qs, obj)
            if path == "/api/cut":
                return handle_post_cut(self, qs, obj)
            if path == "/api/refine":
                return handle_post_refine(self, qs, obj)
            if path == "/api/export":
                return handle_post_export(self, qs, obj)
            if path == "/api/project/create":
                return handle_post_project_create(self, obj)
            if path == "/api/project/add":
                return handle_post_project_add(self, obj)
            if path == "/api/project/remove":
                return handle_post_project_remove(self, obj)
            if path == "/api/rerun":
                return handle_post_rerun(self, qs, obj)
            if path == "/api/transcripts":
                return handle_post_transcripts(self, qs, obj)
            if path == "/api/whisper/install":
                return handle_post_whisper_install(self, qs)
            if path == "/api/whisper/install/cancel":
                return handle_post_whisper_install_cancel(self, qs)
            if path == "/api/whisper/models/delete":
                return handle_post_whisper_model_delete(self, qs, obj)
            if path == "/api/logs/clear":
                clear_session_log()
                return self._send_json({"ok": True})

            return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

        def do_DELETE(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path
            if not self._require_auth():
                return

            if path.startswith("/api/prompts/"):
                name = path[len("/api/prompts/") :]
                return handle_delete_prompt(self, qs, name)
            if path.startswith("/api/providers/"):
                name = path[len("/api/providers/") :]
                return handle_delete_provider(self, qs, name)

            return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

    # Per-project state dict and config cache (set from closure, not class default)
    Handler._project_states = {}
    Handler._config_cache = ConfigCache(config_path, on_load=auto_reindex_if_needed)
    Handler._api_token = api_token
    Handler.DEFAULT_PROJECT = DEFAULT_PROJECT
    Handler.input_dir = input_dir
    Handler.output_dir = output_dir
    Handler.config_path = config_path
    return Handler


def run(
    config: AppConfig,
    config_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    api_token: str | None = None,
) -> int:
    install_hooks()
    import secrets

    TOKEN = api_token
    _is_local = host in ("127.0.0.1", "localhost", "")
    if TOKEN is None:
        if _is_local:
            TOKEN = ""
        else:
            TOKEN = secrets.token_urlsafe(32)
    if TOKEN:
        print(f"  API Token: {TOKEN}")
        print(f"  Token URL: http://{host}:{port}/?token={TOKEN}")
    # Try loading last used project config
    active_config = resolve_last_project_config(config, config_path)
    auto_reindex_if_needed(active_config)
    handler = make_handler(active_config, config_path, api_token=TOKEN)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"  UI started: {url}")
    print(f"  Project directory: {active_config.paths.input_dir}")
    print(f"  Output directory: {active_config.paths.output_dir}")
    if not _is_local:
        if not TOKEN:
            print(f"  ⚠  Listening on {host} — exposed to LAN without auth!")
        else:
            print(f"  ⚠  Listening on {host} — exposed to LAN (auth required)")
    print("  Ctrl+C to exit")
    if open_browser:
        threading.Timer(0.5, lambda: _open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  UI closed")
    finally:
        server.server_close()
        before_stop()
    return 0


def _open_browser(url: str) -> None:
    import webbrowser

    webbrowser.open(url)
