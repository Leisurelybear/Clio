from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clio.processing_state import ProcessingState

if TYPE_CHECKING:
    from clio.ui.handler_protocol import HandlerProtocol


def handle_get_processing_state(handler: HandlerProtocol, qs: dict[str, Any]) -> None:
    proj_dir = handler._resolve_project_dir(qs)
    proj_out = handler._get_project_output(proj_dir)
    state = ProcessingState(proj_out)
    handler._send_json(state.get_state())
