"""Local web UI: video + player + JSON text visualization editing.

- Zero external dependencies: stdlib http.server
- Defaults to 127.0.0.1 only (not exposed to LAN)
- All file IO sandboxed within config.paths.output_dir to prevent path traversal
- Writes use atomic rename, first overwrite leaves a .bak copy
"""

# ruff: noqa: F401 — all handler imports used by router resolver (lazy lookup)
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
from clio.ui.router import Route, Router
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
from clio.ui.routes.fs import (
    handle_get_fs_dirs,
    handle_get_fs_videos,
    handle_post_fs_mkdir,
    handle_post_fs_reveal,
)
from clio.ui.routes.plan import (
    handle_get_plan,
    handle_get_plans,
    handle_post_cut,
    handle_post_plan_readiness,
    handle_put_plan,
)
from clio.ui.routes.processing_state_routes import handle_get_processing_state
from clio.ui.routes.projects import (
    handle_get_project,
    handle_get_projects,
    handle_post_project_add,
    handle_post_project_create,
    handle_post_project_migrate,
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
from clio.ui.routes.videos import (
    handle_get_video,
    handle_get_videos,
    handle_get_videos_selected,
    handle_get_vmeta,
    handle_put_videos_relink,
    handle_put_videos_selected,
)
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
    resolve_project_dir,
    resolve_project_input,
)
from clio.utils import write_json_atomic

STATIC_DIR = Path(__file__).parent / "static"


def _handle_get_logs(handler, qs):
    offset = int(qs.get("offset", ["0"])[0])
    return handler._send_json(read_session_log(offset))


def _handle_post_logs_clear(handler, qs, obj):
    clear_session_log()
    return handler._send_json({"ok": True})


@dataclass
class _ServerState:
    run_lock: threading.Lock = field(default_factory=threading.Lock)
    run_thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


def make_handler(
    config: AppConfig, config_path: Path | None = None, api_token: str = ""
) -> type[BaseHTTPRequestHandler]:
    output_dir = config.paths.output_dir
    project_dir = config.project_dir or Path.cwd()
    static_dir = STATIC_DIR
    project_path = project_dir / "project.json"

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
            if cur.get("name") == output_dir.name and project_dir.name != output_dir.name:
                cur["name"] = project_dir.name
                write_json_atomic(project_path, cur)
        except (json.JSONDecodeError, OSError):
            pass

    DEFAULT_PROJECT = {
        "currentDay": "day1",
        "source": "compressed",
        "name": project_dir.name,
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
        project_dir: Path
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

        def _resolve_project_dir(self, qs: dict) -> Path:
            return resolve_project_dir(qs, project_dir, config_path)

        def _resolve_project_input(self, qs: dict) -> Path:
            """Compat alias for _resolve_project_dir."""
            return self._resolve_project_dir(qs)

        def _get_project_output(self, qs_or_proj_dir: dict | Path) -> Path:
            if isinstance(qs_or_proj_dir, dict):
                proj_dir = self._resolve_project_dir(qs_or_proj_dir)
            else:
                proj_dir = qs_or_proj_dir
            return _project_output_dir(proj_dir)

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

            handler_fn, path_kwargs, route = router.dispatch("GET", path)
            if handler_fn is None:
                return self.send_error(HTTPStatus.NOT_FOUND)

            if route and route.auth_required and not self._require_auth():
                return

            if path_kwargs:
                return handler_fn(self, qs, **path_kwargs)
            return handler_fn(self, qs)

        def do_PUT(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path
            if router.get_policy("PUT", path).auth_required and not self._require_auth():
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                obj = json.loads(raw.decode("utf-8"))
                if not isinstance(obj, dict):
                    raise ValueError("expected a JSON object")
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                return self._send_json({"ok": False, "error": f"invalid JSON: {e}"}, 400)

            handler_fn, path_kwargs, route = router.dispatch("PUT", path)
            if handler_fn is None:
                return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

            if path_kwargs:
                return handler_fn(self, qs, obj, **path_kwargs)
            return handler_fn(self, qs, obj)

        def do_POST(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path
            if router.get_policy("POST", path).auth_required and not self._require_auth():
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                obj = json.loads(raw.decode("utf-8"))
                if not isinstance(obj, dict):
                    raise ValueError("expected a JSON object")
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                return self._send_json({"ok": False, "error": f"invalid JSON: {e}"}, 400)

            handler_fn, path_kwargs, route = router.dispatch("POST", path)
            if handler_fn is None:
                return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

            handler_key = route.handler if isinstance(route.handler, str) else ""
            params = _POST_HANDLER_PARAMS.get(handler_key, {"qs", "obj"})
            call_kwargs: dict[str, Any] = {}
            if "qs" in params:
                call_kwargs["qs"] = qs
            if "obj" in params:
                call_kwargs["obj"] = obj
            call_kwargs.update(path_kwargs)
            return handler_fn(self, **call_kwargs)

        def do_DELETE(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            path = url.path
            if not self._require_auth():
                return

            handler_fn, path_kwargs, route = router.dispatch("DELETE", path)
            if handler_fn is None:
                return self._send_json({"ok": False, "error": "unknown endpoint"}, 404)

            if path_kwargs:
                return handler_fn(self, qs, **path_kwargs)
            return handler_fn(self, qs)

    def _resolve_handler(name: str):
        """Look up handler function from module namespace (supports @patch in tests)."""
        import sys

        return getattr(sys.modules["clio.ui.server"], name, None)

    # Handlers with non-standard POST signatures (no qs or no obj)
    _POST_HANDLER_PARAMS = {
        "handle_post_whisper_install": {"qs"},
        "handle_post_whisper_install_cancel": {"qs"},
        "handle_post_project_create": {"obj"},
        "handle_post_project_add": {"obj"},
        "handle_post_project_remove": {"obj"},
        "handle_post_project_migrate": {"obj"},
        "handle_post_fs_mkdir": {"obj"},
    }

    router = Router(resolver=_resolve_handler)
    router.add_list(
        [
            Route("GET", "/api/config", "handle_get_config"),
            Route("GET", "/api/config/raw", "handle_get_config_raw"),
            Route("GET", "/api/config/global", "handle_get_config_global"),
            Route("GET", "/api/config/project", "handle_get_config_project"),
            Route("GET", "/api/providers", "handle_get_providers"),
            Route("GET", "/api/project", "handle_get_project"),
            Route("GET", "/api/projects", "handle_get_projects"),
            Route("GET", "/api/videos", "handle_get_videos"),
            Route("GET", "/api/video", "handle_get_video"),
            Route("GET", "/api/vmeta/{stem}", "handle_get_vmeta"),
            Route("GET", "/api/videos/selected", "handle_get_videos_selected"),
            Route("PUT", "/api/videos/selected", "handle_put_videos_selected"),
            Route("PUT", "/api/videos/relink", "handle_put_videos_relink"),
            Route("GET", "/api/texts", "handle_get_texts"),
            Route("GET", "/api/voiceover", "handle_get_voiceover"),
            Route("GET", "/api/plans", "handle_get_plans"),
            Route("GET", "/api/run/status", "handle_get_run_status"),
            Route("GET", "/api/run/stream", "handle_get_run_stream"),
            Route("GET", "/api/plan", "handle_get_plan"),
            Route("GET", "/api/processing-state", "handle_get_processing_state"),
            Route("GET", "/api/fs/dirs", "handle_get_fs_dirs"),
            Route("GET", "/api/fs/videos", "handle_get_fs_videos"),
            Route("POST", "/api/fs/mkdir", "handle_post_fs_mkdir"),
            Route("POST", "/api/fs/reveal", "handle_post_fs_reveal"),
            Route("GET", "/api/transcripts", "handle_get_transcripts"),
            Route("GET", "/api/whisper/check", "handle_get_whisper_check"),
            Route("GET", "/api/whisper/install/status", "handle_get_whisper_install_status"),
            Route("GET", "/api/whisper/models", "handle_get_whisper_models"),
            Route("GET", "/api/token-usage", "handle_get_token_usage"),
            Route("GET", "/api/env", "handle_get_env"),
            Route("GET", "/api/prompts", "handle_get_prompts"),
            Route("GET", "/api/logs", "_handle_get_logs"),
            Route("PUT", "/api/config/raw", "handle_put_config_raw"),
            Route("PUT", "/api/config/global", "handle_put_config_global"),
            Route("PUT", "/api/config/project", "handle_put_config_project"),
            Route("PUT", "/api/providers/{name}", "handle_put_provider"),
            Route("PUT", "/api/project", "handle_put_project"),
            Route("PUT", "/api/texts", "handle_put_texts"),
            Route("PUT", "/api/voiceover", "handle_put_voiceover"),
            Route("PUT", "/api/plan", "handle_put_plan"),
            Route("PUT", "/api/transcripts", "handle_put_transcripts"),
            Route("PUT", "/api/whisper/model", "handle_put_whisper_model"),
            Route("PUT", "/api/env", "handle_put_env"),
            Route("PUT", "/api/prompts/{name}", "handle_put_prompt"),
            Route("POST", "/api/run/start", "handle_post_run_start"),
            Route("POST", "/api/webhook/trigger", "handle_post_run_start"),
            Route("POST", "/api/run/preview", "handle_post_run_preview"),
            Route("POST", "/api/run/cancel", "handle_post_run_cancel"),
            Route("POST", "/api/ai/test", "handle_post_ai_test"),
            Route("POST", "/api/config/init", "handle_post_config_init"),
            Route("POST", "/api/providers", "handle_post_provider"),
            Route("POST", "/api/cut", "handle_post_cut"),
            Route("POST", "/api/plan/readiness", "handle_post_plan_readiness"),
            Route("POST", "/api/refine", "handle_post_refine"),
            Route("POST", "/api/export", "handle_post_export"),
            Route("POST", "/api/project/create", "handle_post_project_create"),
            Route("POST", "/api/project/add", "handle_post_project_add"),
            Route("POST", "/api/project/remove", "handle_post_project_remove"),
            Route("POST", "/api/project/migrate", "handle_post_project_migrate"),
            Route("POST", "/api/rerun", "handle_post_rerun"),
            Route("POST", "/api/transcripts", "handle_post_transcripts"),
            Route("POST", "/api/whisper/install", "handle_post_whisper_install"),
            Route("POST", "/api/whisper/install/cancel", "handle_post_whisper_install_cancel"),
            Route("POST", "/api/whisper/models/delete", "handle_post_whisper_model_delete"),
            Route("POST", "/api/logs/clear", "_handle_post_logs_clear"),
            Route("DELETE", "/api/prompts/{name}", "handle_delete_prompt"),
            Route("DELETE", "/api/providers/{name}", "handle_delete_provider"),
        ]
    )

    # Per-project state dict and config cache (set from closure, not class default)
    Handler._project_states = {}
    Handler._config_cache = ConfigCache(config_path, on_load=auto_reindex_if_needed)
    Handler._api_token = api_token
    Handler.DEFAULT_PROJECT = DEFAULT_PROJECT
    Handler.project_dir = project_dir
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
    print(f"  Project directory: {active_config.project_dir or '(none)'}")
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
