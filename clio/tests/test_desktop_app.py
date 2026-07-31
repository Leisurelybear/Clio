# clio/tests/test_desktop_app.py
from __future__ import annotations

import clio.desktop.app as app_mod
from clio.config import AppConfig
from clio.desktop.server_host import (
    fetch_run_status,
    request_run_cancel,
    start_server,
    stop_server,
)


def test_handle_closing_idle_allows_close(monkeypatch):
    monkeypatch.setattr(app_mod, "fetch_run_status", lambda host, port: {"status": "idle", "running": False})
    confirmed = []
    monkeypatch.setattr(app_mod, "request_run_cancel", lambda host, port: confirmed.append(port))
    assert app_mod._handle_closing("127.0.0.1", 1234) is True
    assert confirmed == []


def test_handle_closing_running_confirmed_cancels(monkeypatch):
    monkeypatch.setattr(app_mod, "fetch_run_status", lambda host, port: {"status": "running", "running": True})
    monkeypatch.setattr(app_mod, "_confirm_quit", lambda: True)
    cancelled = []
    monkeypatch.setattr(app_mod, "request_run_cancel", lambda host, port: cancelled.append(port))
    assert app_mod._handle_closing("127.0.0.1", 1234) is True
    assert cancelled == [1234]


def test_handle_closing_running_declined_aborts_close(monkeypatch):
    monkeypatch.setattr(app_mod, "fetch_run_status", lambda host, port: {"status": "running", "running": True})
    monkeypatch.setattr(app_mod, "_confirm_quit", lambda: False)
    cancelled = []
    monkeypatch.setattr(app_mod, "request_run_cancel", lambda host, port: cancelled.append(port))
    assert app_mod._handle_closing("127.0.0.1", 1234) is False
    assert cancelled == []


def test_fetch_run_status_and_cancel_roundtrip(loaded_config: AppConfig, monkeypatch):
    monkeypatch.setattr(
        "clio.desktop.server_host.auto_reindex_if_needed",
        lambda cfg: False,
    )
    handle = start_server(
        loaded_config,
        config_path=None,
        host="127.0.0.1",
        port=0,
        api_token=None,
    )
    try:
        status = fetch_run_status(handle.host, handle.port)
        assert isinstance(status, dict)
        assert "status" in status and "running" in status
        request_run_cancel(handle.host, handle.port)  # no exception while idle
    finally:
        stop_server(handle)


def test_fetch_run_status_unreachable_returns_empty():
    assert fetch_run_status("127.0.0.1", 1) == {}


def test_request_run_cancel_unreachable_silent():
    request_run_cancel("127.0.0.1", 1)  # must not raise
