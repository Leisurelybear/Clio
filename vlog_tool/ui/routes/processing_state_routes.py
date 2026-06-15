from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from vlog_tool.processing_state import ProcessingState

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def handle_get_processing_state(handler: BaseHTTPRequestHandler, qs: dict) -> None:
    proj_input = handler._resolve_project_input(qs)
    proj_out = handler._get_project_output(proj_input)
    state = ProcessingState(proj_out)
    handler._send_json(state.get_state())
