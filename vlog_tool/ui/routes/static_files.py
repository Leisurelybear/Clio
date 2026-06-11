"""Route handlers: /, /index.html, /favicon.ico, /static/*"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_index(handler: BaseHTTPRequestHandler) -> None:
    """Handle GET / or /index.html."""
    handler._send_static("index.html")


def handle_favicon(handler: BaseHTTPRequestHandler) -> None:
    """Handle GET /favicon.ico — return a simple SVG favicon, avoid 404."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📹</text></svg>'
    handler.send_response(200)
    handler.send_header("Content-Type", "image/svg+xml")
    handler.send_header("Cache-Control", "public, max-age=31536000")
    handler.end_headers()
    handler.wfile.write(svg.encode("utf-8"))


def handle_static(handler: BaseHTTPRequestHandler, rel: str) -> None:
    """Handle GET /static/<path>."""
    if ".." in rel or rel.startswith("/"):
        return handler.send_error(HTTPStatus.FORBIDDEN)
    handler._send_static(rel)
