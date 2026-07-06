from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from clio.ui.routes.ai import handle_post_ai_test


def test_ai_test_requires_provider() -> None:
    handler = MagicMock()

    handle_post_ai_test(handler, {}, {"model": "deepseek-chat"})

    handler._send_json.assert_called_once_with({"ok": False, "error": "provider is required"}, 400)
    handler._resolve_project_input.assert_not_called()
    handler._get_config.assert_not_called()


def test_ai_test_rejects_blank_provider(monkeypatch) -> None:
    handler = MagicMock()
    service = MagicMock()
    monkeypatch.setattr("clio.ui.routes.ai.test_provider_connection", service)

    handle_post_ai_test(handler, {}, {"provider": "   ", "model": "deepseek-chat"})

    handler._send_json.assert_called_once_with({"ok": False, "error": "provider is required"}, 400)
    handler._resolve_project_input.assert_not_called()
    handler._get_config.assert_not_called()
    service.assert_not_called()


def test_ai_test_rejects_non_string_provider(monkeypatch) -> None:
    handler = MagicMock()
    service = MagicMock()
    monkeypatch.setattr("clio.ui.routes.ai.test_provider_connection", service)

    handle_post_ai_test(handler, {}, {"provider": 123, "model": "deepseek-chat"})

    handler._send_json.assert_called_once_with({"ok": False, "error": "provider must be a string"}, 400)
    handler._resolve_project_input.assert_not_called()
    handler._get_config.assert_not_called()
    service.assert_not_called()


def test_ai_test_rejects_non_string_model(monkeypatch) -> None:
    handler = MagicMock()
    service = MagicMock()
    monkeypatch.setattr("clio.ui.routes.ai.test_provider_connection", service)

    handle_post_ai_test(handler, {}, {"provider": "deepseek", "model": []})

    handler._send_json.assert_called_once_with({"ok": False, "error": "model must be a string"}, 400)
    handler._resolve_project_input.assert_not_called()
    handler._get_config.assert_not_called()
    service.assert_not_called()


def test_ai_test_calls_service_with_resolved_config(monkeypatch) -> None:
    handler = MagicMock()
    qs = {"input_dir": ["G:/trip"]}
    proj_input = Path("G:/trip")
    cfg = MagicMock()
    result = {"ok": True, "provider": "deepseek", "model": "deepseek-chat"}
    service = MagicMock(return_value=result)
    handler._resolve_project_input.return_value = proj_input
    handler._get_config.return_value = cfg
    monkeypatch.setattr("clio.ui.routes.ai.test_provider_connection", service)

    handle_post_ai_test(
        handler,
        qs,
        {"provider": " deepseek ", "model": " deepseek-chat "},
    )

    handler._resolve_project_input.assert_called_once_with(qs)
    handler._get_config.assert_called_once_with(proj_input)
    service.assert_called_once_with(cfg, provider_name="deepseek", model="deepseek-chat")
    handler._send_json.assert_called_once_with(result)


def test_ai_test_passes_missing_model_as_none(monkeypatch) -> None:
    handler = MagicMock()
    cfg = MagicMock()
    service = MagicMock(return_value={"ok": True})
    handler._resolve_project_input.return_value = Path("G:/trip")
    handler._get_config.return_value = cfg
    monkeypatch.setattr("clio.ui.routes.ai.test_provider_connection", service)

    handle_post_ai_test(handler, {}, {"provider": "deepseek"})

    service.assert_called_once_with(cfg, provider_name="deepseek", model="")
    handler._send_json.assert_called_once_with({"ok": True})
