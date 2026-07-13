from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from clio.ui.routes.token_routes import handle_get_token_usage


class TestHandleGetTokenUsage:
    def test_returns_stats(self, tmp_path):
        handler = MagicMock()
        handler._resolve_project_dir.return_value = tmp_path
        handler._send_json = MagicMock()

        handle_get_token_usage(handler, {})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args.args[0]
        assert "total" in payload
        assert payload["total"]["total_tokens"] == 0
        assert "by_model" in payload
        assert "by_task" in payload
        assert "history" in payload

    def test_project_output_is_none_returns_error(self):
        handler = MagicMock()
        handler._resolve_project_dir.return_value = Path("/some/project")
        handler._send_json = MagicMock()

        with patch("clio.ui.routes.token_routes._project_output_dir", return_value=None):
            handle_get_token_usage(handler, {})

        handler._send_json.assert_called_once_with({"ok": False, "error": "no project"})
