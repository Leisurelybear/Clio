# clio/tests/test_desktop_single_instance.py
from __future__ import annotations

import json
import urllib.error

from clio.desktop.single_instance import (
    WEB_PORT,
    focus_first_instance,
    is_web_running,
    lock_path,
    read_lock,
    remove_lock,
    write_lock,
)

# ---------------------------------------------------------------------------
# lock file helpers
# ---------------------------------------------------------------------------


def test_lock_path_is_inside_config_dir(tmp_path):
    assert lock_path(tmp_path) == tmp_path / "clio.lock"


def test_read_lock_missing_returns_none(tmp_path):
    assert read_lock(tmp_path) is None


def test_write_then_read_roundtrip(tmp_path):
    write_lock(tmp_path, port=4321, pid=12345)
    data = read_lock(tmp_path)
    assert data is not None
    assert data["port"] == 4321
    assert data["pid"] == 12345


def test_read_lock_corrupt_returns_none(tmp_path):
    (tmp_path / "clio.lock").write_text("not-json{{{", encoding="utf-8")
    assert read_lock(tmp_path) is None


def test_read_lock_non_dict_returns_none(tmp_path):
    (tmp_path / "clio.lock").write_text(json.dumps(["x"]), encoding="utf-8")
    assert read_lock(tmp_path) is None


def test_remove_lock_deletes_file(tmp_path):
    write_lock(tmp_path, port=4321, pid=1)
    assert (tmp_path / "clio.lock").is_file()
    remove_lock(tmp_path)
    assert not (tmp_path / "clio.lock").exists()


def test_remove_lock_missing_is_silent(tmp_path):
    remove_lock(tmp_path)  # must not raise


# ---------------------------------------------------------------------------
# focus probe
# ---------------------------------------------------------------------------


def test_focus_first_instance_unreachable_returns_false(monkeypatch):
    def _refuse(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _refuse)
    assert focus_first_instance("127.0.0.1", 9) is False


def test_focus_first_instance_http_error_means_alive(monkeypatch):
    """Any HTTP response (even 5xx while the window is not ready) proves the
    first instance is alive; the second instance must exit instead of taking over."""

    def _raise_http(*args, **kwargs):
        raise urllib.error.HTTPError("url", 500, "not ready", None, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise_http)
    assert focus_first_instance("127.0.0.1", 9) is True


def test_focus_first_instance_ok_means_alive(monkeypatch):
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    assert focus_first_instance("127.0.0.1", 9) is True


def test_focus_first_instance_builds_post_request(monkeypatch):
    captured = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _urlopen(req, **kwargs):
        captured["method"] = req.method
        captured["data"] = req.data
        captured["url"] = req.full_url
        captured["timeout"] = kwargs.get("timeout")
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    assert focus_first_instance("127.0.0.1", 5555, timeout=2) is True
    assert captured["url"] == "http://127.0.0.1:5555/api/desktop/focus"
    assert captured["method"] == "POST"
    assert captured["data"] == b"{}"
    assert captured["timeout"] == 2


# ---------------------------------------------------------------------------
# web version detection
# ---------------------------------------------------------------------------


def test_is_web_running_false_when_unreachable(monkeypatch):
    def _refuse(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _refuse)
    assert is_web_running("127.0.0.1", 1) is False


def test_is_web_running_true_for_clio_index(monkeypatch):
    class _Resp:
        status = 200

        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n):
            return self._body[:n]

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _Resp(b"<title>Vlog \xe5\x89\xaa\xe8\xbe\x91 UI</title>"),
    )
    assert is_web_running("127.0.0.1", WEB_PORT) is True


def test_is_web_running_false_for_unrelated_server(monkeypatch):
    class _Resp:
        status = 200

        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n):
            return self._body[:n]

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp(b"<html>apache</html>"))
    assert is_web_running("127.0.0.1", WEB_PORT) is False


def test_is_web_running_non_200_false(monkeypatch):
    class _Resp:
        status = 403

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n):
            return b""

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    assert is_web_running("127.0.0.1", WEB_PORT) is False
