import json
import sys
import types

from api.tts_edge import handle_edge_tts_audio


class _Handler:
    def __init__(self):
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)

    def header(self, name):
        for key, value in self.sent_headers:
            if key.lower() == name.lower():
                return value
        return None


def _json_response(handler, payload, status=200, extra_headers=None):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    if extra_headers:
        for key, value in extra_headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    handler.write(body)


def _security_headers(handler):
    handler.send_header("X-Content-Type-Options", "nosniff")


def _payload(handler):
    return json.loads(handler.body.decode("utf-8"))


def _call(body):
    handler = _Handler()
    result = handle_edge_tts_audio(
        handler,
        body,
        json_response=_json_response,
        security_headers=_security_headers,
    )
    return result, handler


def test_edge_tts_empty_input_returns_400():
    result, handler = _call({"input": "   "})

    assert result is True
    assert handler.status == 400
    assert "required" in _payload(handler)["error"]


def test_edge_tts_too_long_returns_400():
    result, handler = _call({"input": "x" * 5001})

    assert result is True
    assert handler.status == 400
    assert "5000" in _payload(handler)["error"]


def test_edge_tts_missing_dependency_returns_503(monkeypatch):
    import api.tts_edge as tts_edge

    def missing_dependency(_name):
        raise ImportError("edge_tts unavailable")

    monkeypatch.setattr(tts_edge.importlib, "import_module", missing_dependency)

    result, handler = _call({"input": "hello"})

    assert result is True
    assert handler.status == 503
    assert _payload(handler)["missing_dependency"] == "edge-tts"


def test_edge_tts_success_returns_audio_mpeg(monkeypatch):
    captured = {}

    class Communicate:
        def __init__(self, text, voice, rate, pitch):
            captured.update({"text": text, "voice": voice, "rate": rate, "pitch": pitch})

        async def stream(self):
            yield {"type": "audio", "data": b"mp3-"}
            yield {"type": "WordBoundary", "offset": 0}
            yield {"type": "audio", "data": b"bytes"}

    module = types.SimpleNamespace(Communicate=Communicate)
    monkeypatch.setitem(sys.modules, "edge_tts", module)

    result, handler = _call(
        {
            "text": "hello",
            "voice": "en-US-JennyNeural",
            "rate": "1.2",
            "pitch": "0.8",
        }
    )

    assert result is True
    assert handler.status == 200
    assert handler.header("Content-Type") == "audio/mpeg"
    assert handler.header("Content-Length") == str(len(b"mp3-bytes"))
    assert handler.header("X-Content-Type-Options") == "nosniff"
    assert bytes(handler.body) == b"mp3-bytes"
    assert captured == {
        "text": "hello",
        "voice": "en-US-JennyNeural",
        "rate": "+20%",
        "pitch": "-10Hz",
    }


def test_tts_route_registry_is_registered():
    import api.routes as routes

    assert "/api/tts/edge/audio/speech" in routes._ROUTE_REGISTRY.post_routes


def test_frontend_edge_tts_static_wiring():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    panels = (root / "static" / "panels.js").read_text(encoding="utf-8")
    ui = (root / "static" / "ui.js").read_text(encoding="utf-8")
    edge = (root / "static" / "tts-edge.js").read_text(encoding="utf-8")
    i18n = (root / "static" / "i18n.js").read_text(encoding="utf-8")

    assert 'static/tts-edge.js?v=__WEBUI_VERSION__' in html
    assert 'id="settingsTtsProvider"' in html
    assert 'id="settingsTtsEdgeVoice"' in html
    assert 'list="settingsTtsEdgeVoiceOptions"' in html
    assert 'id="settingsTtsEdgeVoiceOptions"' in html
    assert 'id="settingsTtsVoiceField"' in html
    assert html.index('id="settingsTtsVoice"') < html.index('id="settingsTtsEdgeVoice"') < html.index('id="settingsTtsRate"')
    assert 'id="settingsTtsVoice" data-tts-provider-control="browser"' in html
    assert 'id="settingsTtsEdgeVoice" data-tts-provider-control="edge"' in html
    for voice in (
        "en-US-AriaNeural",
        "en-US-JennyNeural",
        "zh-CN-XiaoxiaoNeural",
        "zh-CN-YunxiNeural",
        "zh-HK-HiuGaaiNeural",
        "zh-TW-HsiaoChenNeural",
        "ja-JP-NanamiNeural",
        "ko-KR-SunHiNeural",
    ):
        assert f'<option value="{voice}"></option>' in html
    assert "hermes-tts-provider" in panels
    assert "hermes-tts-edge-voice" in panels
    assert "applyTtsProviderUi" in panels
    assert "$('settingsTtsVoiceLabel')" in panels
    assert "settings_label_tts_edge_voice" in panels
    assert "settingsTtsEdgeVoice" in panels
    assert "window.HermesEdgeTTS" in ui
    assert "SpeechSynthesisUtterance" in ui
    assert "api/tts/edge/audio/speech" in edge
    assert "localStorage.getItem('hermes-tts-provider')" in edge
    assert "localStorage.getItem('hermes-tts-voice')" not in edge
    for key in (
        "settings_label_tts_provider",
        "settings_tts_provider_browser",
        "settings_tts_provider_edge",
        "settings_label_tts_voice",
        "settings_desc_tts_edge_voice",
        "tts_edge_failed",
    ):
        assert key in i18n


def test_frontend_edge_tts_rejects_non_audio_json_before_audio():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    edge = (root / "static" / "tts-edge.js").read_text(encoding="utf-8")

    assert "function responseContentType(res)" in edge
    assert "function responseErrorMessage(res, fallback)" in edge
    assert "function isAudioContentType(type)" in edge
    assert "body.error||body.message" in edge
    assert "if(!isAudioContentType(type))" in edge
    assert "Edge TTS returned a non-audio response." in edge
    assert edge.index("if(!isAudioContentType(type))") < edge.index("const blob=await res.blob()")
    assert edge.index("const blob=await res.blob()") < edge.index("await playBlob(blob)")


def test_frontend_edge_tts_audio_blob_type_and_lifecycle():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    edge = (root / "static" / "tts-edge.js").read_text(encoding="utf-8")

    assert "if(!blob||!blob.size)" in edge
    assert "new Blob([blob],{type:type||'audio/mpeg'})" in edge
    assert "function blobTypeCandidates(blob)" in edge
    assert "add('audio/mpeg')" in edge
    assert "add('audio/mp3')" in edge
    assert "add('')" in edge
    assert "function waitForPlayable(audio)" in edge
    assert "audio.addEventListener('canplay',onReady,{once:true})" in edge
    assert "audio.addEventListener('loadedmetadata',onReady,{once:true})" in edge
    assert "if(typeof audio.load==='function') audio.load()" in edge
    assert "function mediaErrorMessage(audio)" in edge
    assert "unsupported source" in edge
    assert "function cleanupPlayback()" in edge
    assert "currentAudio.onended=cleanupPlayback" in edge
    assert "currentAudio.onerror=function()" in edge
    assert "Browser audio error" in edge
    assert "URL.revokeObjectURL(currentUrl)" in edge
    assert edge.index("await waitForPlayable(currentAudio)") < edge.index("await currentAudio.play()")
    play_start = edge.index("async function playBlob(blob)")
    play_body = edge[play_start:edge.index("async function fetchAudio(text)")]
    assert play_body.index("await currentAudio.play()") < play_body.index("return;")


def test_frontend_edge_tts_does_not_revoke_before_play_settles():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    edge = (root / "static" / "tts-edge.js").read_text(encoding="utf-8")

    play_start = edge.index("async function playBlob(blob)")
    play_body = edge[play_start:edge.index("async function fetchAudio(text)")]
    assert "currentUrl=url" in play_body
    assert "await currentAudio.play()" in play_body
    assert "URL.revokeObjectURL(url)" in play_body
    assert play_body.index("await currentAudio.play()") < play_body.index("URL.revokeObjectURL(url)")
