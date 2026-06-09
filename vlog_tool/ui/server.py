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
from vlog_tool.pipeline import run_cut_all, run_pipeline_steps

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
    output_dir = config.paths.output_dir   # 默认输出目录（来自 config.yaml）
    input_dir = config.paths.input_dir       # 项目根目录（素材目录）
    static_dir = STATIC_DIR
    project_path = input_dir / "project.json"

    # 兼容旧版：如果新位置没有 project.json，从旧位置迁移
    old_project_path = output_dir / "project.json"
    if not project_path.is_file() and old_project_path.is_file():
        try:
            shutil.copy2(old_project_path, project_path)
        except OSError:
            pass
    # 迁移后修复 name：如果 name 是旧 output_dir 的名称，改为 input_dir 名称
    if project_path.is_file():
        try:
            cur = json.loads(project_path.read_text(encoding="utf-8"))
            if cur.get("name") == output_dir.name and input_dir.name != output_dir.name:
                cur["name"] = input_dir.name
                project_path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass

    DEFAULT_PROJECT = {
        "currentDay": "day1",
        "source": "compressed",
        "name": input_dir.name,
        "output_dir": str(output_dir.resolve()),  # 默认输出目录
        "lastEntity": None,
        "lastVideo": None,
    }

    def _project_output_dir(proj_input_dir: Path) -> Path:
        """根据 project.json 或默认值返回项目的输出目录。"""
        proj_file = proj_input_dir / "project.json"
        if proj_file.is_file():
            try:
                data = json.loads(proj_file.read_text(encoding="utf-8"))
                out = data.get("output_dir") or "output"
            except (json.JSONDecodeError, OSError):
                out = "output"
        else:
            out = "output"
        out_path = Path(out)
        if not out_path.is_absolute():
            out_path = (proj_input_dir / out_path).resolve()
        return out_path

    def _detect_steps(proj_output_dir: Path) -> dict:
        """从文件系统推断各 pipeline 步骤是否已完成。"""
        steps = {}
        if not proj_output_dir.is_dir():
            return {k: False for k in ("compress", "analyze", "scripts", "plan", "label", "cut")}
        comp = proj_output_dir / "compressed"
        try:
            steps["compress"] = comp.is_dir() and any(comp.iterdir())
        except (PermissionError, OSError):
            steps["compress"] = False
        texts = [d for d in proj_output_dir.iterdir() if d.is_dir() and d.name.startswith("texts")]
        try:
            steps["analyze"] = any(t.iterdir() for t in texts)
        except (PermissionError, OSError):
            steps["analyze"] = False
        scripts_dir = proj_output_dir / "scripts"
        try:
            steps["scripts"] = scripts_dir.is_dir() and any(scripts_dir.iterdir())
        except (PermissionError, OSError):
            steps["scripts"] = False
        plans_dir = proj_output_dir / "plans"
        try:
            steps["plan"] = plans_dir.is_dir() and any(plans_dir.iterdir())
        except (PermissionError, OSError):
            steps["plan"] = False
        try:
            steps["label"] = (proj_output_dir / "labeled").is_dir() and any((proj_output_dir / "labeled").iterdir())
        except (PermissionError, OSError):
            steps["label"] = False
        try:
            steps["cut"] = (proj_output_dir / "cuts").is_dir() and any((proj_output_dir / "cuts").iterdir())
        except (PermissionError, OSError):
            steps["cut"] = False
        return steps

    def _registry_path() -> Path:
        if config_path:
            return config_path.parent / "projects.json"
        return Path("projects.json")

    def _add_to_registry(dir_path: str) -> None:
        registry_file = _registry_path()
        paths: list[str] = []
        if registry_file.is_file():
            try:
                reg = json.loads(registry_file.read_text(encoding="utf-8"))
                paths = reg.get("projects", [])
            except (json.JSONDecodeError, OSError):
                paths = []
        normalized = str(Path(dir_path).resolve())
        if normalized not in paths:
            paths.append(normalized)
        data = json.dumps({"projects": paths}, ensure_ascii=False, indent=2).encode("utf-8")
        _save_atomic(registry_file, data)

    def _list_projects(current_project_name: str | None = None) -> list[dict]:
        """列出所有可用项目。"""
        projects: list[dict] = []
        seen_dirs: set[str] = set()

        # 1. 从注册文件读已知项目
        registry_file = _registry_path()
        registered_paths: list[str] = []
        if registry_file.is_file():
            try:
                reg = json.loads(registry_file.read_text(encoding="utf-8"))
                registered_paths = reg.get("projects", [])
            except (json.JSONDecodeError, OSError):
                registered_paths = []
        for p_str in registered_paths:
            p = Path(p_str)
            proj_file = p / "project.json"
            if not proj_file.is_file():
                continue
            try:
                data = json.loads(proj_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            name = data.get("name") or p.name
            proj_out = _project_output_dir(p)
            seen_dirs.add(str(p.resolve()))
            projects.append({
                "name": name,
                "input_dir": str(p),
                "output_dir": str(proj_out),
                "currentDay": data.get("currentDay", "day1"),
                "source": data.get("source", "compressed"),
                "steps": _detect_steps(proj_out),
                "createdAt": data.get("createdAt"),
                "updatedAt": data.get("updatedAt"),
                "is_current": (
                    name == current_project_name
                    if current_project_name
                    else p.resolve() == input_dir.resolve()
                ),
            })

        # 2. 扫描 input_dir 的相邻目录（自动发现）
        projects_root = input_dir.parent
        if projects_root.is_dir():
            for p in sorted(projects_root.iterdir()):
                if not p.is_dir():
                    continue
                proj_file = p / "project.json"
                if not proj_file.is_file():
                    continue
                res = p.resolve()
                if str(res) in seen_dirs:
                    continue
                try:
                    data = json.loads(proj_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    data = {}
                name = data.get("name") or p.name
                proj_out = _project_output_dir(p)
                projects.append({
                    "name": name,
                    "input_dir": str(p),
                    "output_dir": str(proj_out),
                    "currentDay": data.get("currentDay", "day1"),
                    "source": data.get("source", "compressed"),
                    "steps": _detect_steps(proj_out),
                    "createdAt": data.get("createdAt"),
                    "updatedAt": data.get("updatedAt"),
                    "is_current": (
                        name == current_project_name
                        if current_project_name
                        else p.resolve() == input_dir.resolve()
                    ),
                })

        # 3. 始终包含当前 input_dir（兜底）
        cur_resolved = str(input_dir.resolve())
        if cur_resolved not in seen_dirs:
            proj_file = input_dir / "project.json"
            if proj_file.is_file():
                try:
                    data = json.loads(proj_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    data = {}
            else:
                data = {}
            name = data.get("name") or input_dir.name
            proj_out = _project_output_dir(input_dir)
            projects.append({
                "name": name,
                "input_dir": str(input_dir),
                "output_dir": str(proj_out),
                "currentDay": data.get("currentDay", "day1"),
                "source": data.get("source", "compressed"),
                "steps": _detect_steps(proj_out),
                "createdAt": data.get("createdAt"),
                "updatedAt": data.get("updatedAt"),
                "is_current": name == current_project_name if current_project_name else True,
            })

        return projects

    class Handler(BaseHTTPRequestHandler):
        # 共享状态（类级别，跨实例）
        _run_lock = threading.Lock()
        _run_thread: threading.Thread | None = None
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

        def _resolve_project_dir(self, qs: dict) -> Path:
            """从查询参数解析项目目录，默认使用当前 output_dir。"""
            project_name = qs.get("project", [None])[0]
            if not project_name:
                return output_dir
            projects_root = output_dir.parent
            # 遍历子目录，读取 project.json 匹配 name
            if projects_root.is_dir():
                for p in projects_root.iterdir():
                    if not p.is_dir():
                        continue
                    proj_file = p / "project.json"
                    if not proj_file.is_file():
                        continue
                    try:
                        data = json.loads(proj_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        continue
                    if data.get("name") == project_name:
                        return p
            return output_dir

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
            if path == "/favicon.ico":
                # 返回简单的 SVG favicon，避免 404
                svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📹</text></svg>'
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Cache-Control", "public, max-age=31536000")
                self.end_headers()
                self.wfile.write(svg.encode("utf-8"))
                return
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                if ".." in rel or rel.startswith("/"):
                    return self.send_error(HTTPStatus.FORBIDDEN)
                return self._send_static(rel)

            if path == "/api/config":
                proj_dir = self._resolve_project_dir(qs)
                comp = proj_dir / "compressed"
                texts = _find_texts_dirs(proj_dir)
                return self._send_json({
                    "input_dir": str(input_dir),  # input_dir is shared for now
                    "output_dir": str(proj_dir),
                    "compressed_dir": str(comp),
                    "texts_dirs": [str(d) for d in texts],
                    "scripts_dir": str(proj_dir / "scripts"),
                    "plans_dir": str(proj_dir / "plans"),
                })

            if path == "/api/config/raw":
                if not config_path or not config_path.is_file():
                    return self._send_json({"error": "config file not available"}, 500)
                with open(config_path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                return self._send_json(raw)

            if path == "/api/project":
                proj_dir = self._resolve_project_dir(qs)
                proj_file = proj_dir / "project.json"
                data = {}
                if proj_file.is_file():
                    try:
                        data = json.loads(proj_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        data = {}
                merged = {**DEFAULT_PROJECT, **data}
                merged["steps"] = _detect_steps(proj_dir)
                return self._send_json(merged)

            if path == "/api/projects":
                req_project = qs.get("project", [None])[0]
                return self._send_json({"projects": _list_projects(req_project)})

            if path == "/api/videos":
                proj_dir = self._resolve_project_dir(qs)
                source = qs.get("source", ["compressed"])[0]
                if source not in ("compressed", "original"):
                    return self._send_json(
                        {"ok": False, "error": "source must be compressed|original"}, 400
                    )
                comp_dir = proj_dir / "compressed"
                # texts/scripts sidecars are keyed by the compressed index in both views
                text_sidecars: dict[str, list[str]] = {}
                for td in _find_texts_dirs(proj_dir):
                    for f in td.iterdir():
                        if f.suffix != ".json" or "_" not in f.stem:
                            continue
                        idx = f.stem.split("_", 1)[0]
                        text_sidecars.setdefault(idx, []).append(f.name)
                script_sidecars: dict[str, list[str]] = {}
                sd = proj_dir / "scripts"
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
                proj_dir = self._resolve_project_dir(qs)
                fname = qs.get("file", [""])[0]
                source = qs.get("source", ["compressed"])[0]
                if not _is_safe_basename(fname):
                    return self.send_error(HTTPStatus.FORBIDDEN)
                if source == "original":
                    vp = input_dir / fname
                else:
                    vp = proj_dir / "compressed" / fname
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

            if path == "/api/plans":
                proj_dir = self._resolve_project_dir(qs)
                plans_dir = proj_dir / "plans"
                plans = []
                if plans_dir.is_dir():
                    for p in sorted(plans_dir.glob("*_plan.json")):
                        day_label = p.stem.replace("_plan", "")
                        if day_label:
                            plans.append({"day_label": day_label, "path": str(p)})
                return self._send_json({"plans": plans})

            if path == "/api/run/status":
                progress_file = output_dir / ".progress.json"
                if progress_file.is_file():
                    try:
                        data = json.loads(progress_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        data = {"status": "unknown"}
                else:
                    data = {"status": "idle"}
                data["running"] = self._run_thread is not None and self._run_thread.is_alive()
                return self._send_json(data)

            if path == "/api/plan":
                day = qs.get("day", [""])[0]
                if not _is_safe_basename(day) or not day:
                    return self._send_json({"error": "forbidden"}, 403)
                p = output_dir / "plans" / f"{day}_plan.json"
                if not p.is_file():
                    return self._send_json({"error": f"规划文件不存在: {p}"}, 404)
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

            if path == "/api/project":
                import datetime
                proj_dir = self._resolve_project_dir(qs)
                proj_file = proj_dir / "project.json"
                data = {}
                if proj_file.is_file():
                    try:
                        data = json.loads(proj_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        data = {}
                merged = {**DEFAULT_PROJECT, **data, **obj}
                merged["updatedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
                if not proj_file.is_file():
                    merged["createdAt"] = merged["updatedAt"]
                proj_dir.mkdir(parents=True, exist_ok=True)
                proj_file.write_text(
                    json.dumps(merged, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return self._send_json({"ok": True})

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

        def do_POST(self):
            url = urlparse(self.path)
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
                if self._run_thread is not None and self._run_thread.is_alive():
                    return self._send_json({"ok": False, "error": "流水线正在运行中"}, 409)
                day_label = obj.get("day_label", "day1")
                steps = obj.get("steps")
                def _run():
                    try:
                        run_pipeline_steps(config, day_label, steps)
                    except Exception:
                        pass
                self._run_thread = threading.Thread(target=_run, daemon=True)
                self._run_thread.start()
                label = "+".join(steps) if steps else "全部"
                return self._send_json({"ok": True, "message": f"流水线已启动（{label}）"})

            if path == "/api/cut":
                day_label = obj.get("day_label", "day1")
                source = obj.get("source", "compressed")
                reencode = obj.get("reencode", False)
                out_dir_raw = obj.get("output_dir", None)

                if source not in ("compressed", "original"):
                    return self._send_json({"ok": False, "error": "source must be compressed|original"}, 400)

                out_path = Path(out_dir_raw) if out_dir_raw else None

                try:
                    run_cut_all(
                        config,
                        day_label=day_label,
                        output_dir=out_path,
                        reencode=bool(reencode),
                        source=source,
                    )
                except Exception as e:
                    return self._send_json({"ok": False, "error": str(e)}, 500)

                actual_out = str(out_path or (output_dir / "cuts" / day_label))
                return self._send_json({
                    "ok": True,
                    "output_dir": actual_out,
                    "day_label": day_label,
                })

            if path == "/api/project/create":
                import datetime
                name = (obj.get("name") or "").strip()
                input_dir_raw = (obj.get("input_dir") or "").strip()
                output_dir_raw = (obj.get("output_dir") or "").strip()
                if not name:
                    return self._send_json({"ok": False, "error": "name is required"}, 400)
                if not input_dir_raw:
                    return self._send_json({"ok": False, "error": "input_dir is required"}, 400)
                input_path = Path(input_dir_raw)
                if not input_path.is_dir():
                    return self._send_json({"ok": False, "error": f"input_dir not found: {input_dir_raw}"}, 400)
                if output_dir_raw:
                    proj_out = Path(output_dir_raw)
                else:
                    proj_out = input_path / "output"
                now = datetime.datetime.now().isoformat(timespec="seconds")
                proj_data = {
                    "name": name,
                    "output_dir": str(proj_out),
                    "currentDay": "day1",
                    "source": "compressed",
                    "lastEntity": None,
                    "lastVideo": None,
                    "createdAt": now,
                    "updatedAt": now,
                }
                proj_file = input_path / "project.json"
                proj_file.write_text(
                    json.dumps(proj_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                _add_to_registry(str(input_path))
                return self._send_json({"ok": True, "project": {"name": name, "input_dir": str(input_path), "output_dir": str(proj_out)}})

            if path == "/api/project/add":
                input_dir_raw = (obj.get("input_dir") or "").strip()
                if not input_dir_raw:
                    return self._send_json({"ok": False, "error": "input_dir is required"}, 400)
                input_path = Path(input_dir_raw)
                proj_file = input_path / "project.json"
                if not proj_file.is_file():
                    return self._send_json({"ok": False, "error": f"指定目录下没有 project.json: {input_dir_raw}"}, 400)
                try:
                    data = json.loads(proj_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as e:
                    return self._send_json({"ok": False, "error": f"无法读取 project.json: {e}"}, 400)
                name = data.get("name") or input_path.name
                _add_to_registry(str(input_path))
                return self._send_json({"ok": True, "project": {"name": name, "input_dir": str(input_path)}})

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
