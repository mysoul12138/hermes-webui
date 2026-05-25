"""Optional Edge TTS audio endpoint.

The dependency is intentionally imported lazily so a normal WebUI install keeps
working without edge-tts. When installed, this module returns MP3 bytes compatible
with OpenAI-style audio clients.
"""

from __future__ import annotations

import asyncio
import importlib
import re
from typing import Any


MAX_TTS_INPUT_CHARS = 5000
DEFAULT_EDGE_TTS_VOICE = "en-US-AriaNeural"

_PERCENT_RE = re.compile(r"^[+-]?\d+%$")
_HERTZ_RE = re.compile(r"^[+-]?\d+Hz$")


def _load_edge_tts():
    try:
        return importlib.import_module("edge_tts")
    except ImportError:
        return None


def _normalize_text(body: dict[str, Any]) -> str:
    value = body.get("input", body.get("text", ""))
    return str(value or "").strip()


def _normalize_voice(value: Any) -> str:
    voice = str(value or "").strip()
    return voice or DEFAULT_EDGE_TTS_VOICE


def _normalize_rate(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "+0%"
    if _PERCENT_RE.match(raw):
        if not raw.startswith(("+", "-")):
            return f"+{raw}"
        return raw
    try:
        numeric = max(0.5, min(2.0, float(raw)))
    except (TypeError, ValueError):
        return "+0%"
    percent = round((numeric - 1.0) * 100)
    return f"{percent:+d}%"


def _normalize_pitch(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "+0Hz"
    if _HERTZ_RE.match(raw):
        if not raw.startswith(("+", "-")):
            return f"+{raw}"
        return raw
    try:
        numeric = max(0.0, min(2.0, float(raw)))
    except (TypeError, ValueError):
        return "+0Hz"
    hertz = round((numeric - 1.0) * 50)
    return f"{hertz:+d}Hz"


async def _synthesize_mp3(edge_tts, *, text: str, voice: str, rate: str, pitch: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if isinstance(chunk, dict) and chunk.get("type") == "audio":
            data = chunk.get("data")
            if isinstance(data, bytes):
                chunks.append(data)
    return b"".join(chunks)


def handle_edge_tts_audio(handler, body: dict[str, Any], *, json_response, security_headers) -> bool:
    text = _normalize_text(body if isinstance(body, dict) else {})
    if not text:
        json_response(handler, {"error": "TTS input text is required."}, status=400)
        return True
    if len(text) > MAX_TTS_INPUT_CHARS:
        json_response(
            handler,
            {"error": f"TTS input must be {MAX_TTS_INPUT_CHARS} characters or fewer."},
            status=400,
        )
        return True

    edge_tts = _load_edge_tts()
    if edge_tts is None:
        json_response(
            handler,
            {
                "error": "Edge TTS is not available. Install the optional edge-tts package to enable this provider.",
                "missing_dependency": "edge-tts",
            },
            status=503,
        )
        return True

    try:
        audio = asyncio.run(
            _synthesize_mp3(
                edge_tts,
                text=text,
                voice=_normalize_voice(body.get("voice")),
                rate=_normalize_rate(body.get("rate")),
                pitch=_normalize_pitch(body.get("pitch")),
            )
        )
    except Exception as exc:
        json_response(handler, {"error": f"Edge TTS synthesis failed: {exc}"}, status=502)
        return True

    if not audio:
        json_response(handler, {"error": "Edge TTS returned no audio."}, status=502)
        return True

    handler.send_response(200)
    handler.send_header("Content-Type", "audio/mpeg")
    handler.send_header("Content-Length", str(len(audio)))
    handler.send_header("Cache-Control", "no-store")
    security_headers(handler)
    handler.end_headers()
    handler.wfile.write(audio)
    return True
