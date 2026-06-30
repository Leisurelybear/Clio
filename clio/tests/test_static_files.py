from __future__ import annotations

from http import HTTPStatus
from unittest.mock import MagicMock

from clio.ui.routes.static_files import handle_favicon, handle_index, handle_static


class TestHandleIndex:
    def test_calls_send_static(self):
        handler = MagicMock()
        handle_index(handler)
        handler._send_static.assert_called_once_with("index.html")


class TestHandleFavicon:
    def test_returns_svg(self):
        handler = MagicMock()
        handle_favicon(handler)
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Content-Type", "image/svg+xml")
        handler.send_header.assert_any_call("Cache-Control", "public, max-age=31536000")
        handler.end_headers.assert_called_once()
        handler.wfile.write.assert_called_once()
        written = handler.wfile.write.call_args.args[0]
        assert written.startswith(b"<svg")
        assert b'xmlns="http://www.w3.org/2000/svg"' in written


class TestHandleStatic:
    def test_valid_rel_calls_send_static(self):
        handler = MagicMock()
        handle_static(handler, "js/app.js")
        handler._send_static.assert_called_once_with("js/app.js")

    def test_dotdot_returns_403(self):
        handler = MagicMock()
        handle_static(handler, "../etc/passwd")
        handler.send_error.assert_called_once_with(HTTPStatus.FORBIDDEN)

    def test_slash_prefix_returns_403(self):
        handler = MagicMock()
        handle_static(handler, "/etc/passwd")
        handler.send_error.assert_called_once_with(HTTPStatus.FORBIDDEN)
