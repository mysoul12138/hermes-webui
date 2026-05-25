"""TTS route registration kept outside ``api.routes``."""

from __future__ import annotations

from api.route_registry import RouteRegistry
from api.tts_edge import handle_edge_tts_audio


def register_tts_routes(registry: RouteRegistry) -> None:
    registry.post("/api/tts/edge/audio/speech", _post_edge_tts_audio)


def _post_edge_tts_audio(handler, _parsed, body: dict, ctx):
    return handle_edge_tts_audio(
        handler,
        body,
        json_response=ctx.j,
        security_headers=ctx._security_headers,
    )
