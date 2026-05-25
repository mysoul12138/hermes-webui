import json
from io import BytesIO
from urllib.parse import urlparse


class _Handler:
    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = BytesIO(raw)
        self.status = None
        self.payload = None


def _install_json_capture(monkeypatch):
    import api.routes as routes

    def fake_json(handler, payload, status=200, extra_headers=None):
        handler.status = status
        handler.payload = payload
        return payload

    monkeypatch.setattr(routes, "j", fake_json)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)


def test_weixin_qrcode_get_route_returns_reference_shape(monkeypatch):
    import api.routes as routes
    import api.weixin as weixin

    _install_json_capture(monkeypatch)
    monkeypatch.setattr(
        weixin,
        "get_qrcode_payload",
        lambda: ({"qrcode": "qr-1", "qrcode_url": "https://example.test/qr.png"}, 200),
    )
    handler = _Handler()

    handled = routes.handle_get(handler, urlparse("/api/hermes/weixin/qrcode"))

    assert handled == {"qrcode": "qr-1", "qrcode_url": "https://example.test/qr.png"}
    assert handler.status == 200


def test_weixin_qrcode_payload_maps_image_compat_fields(monkeypatch):
    import api.weixin as weixin

    monkeypatch.setattr(
        weixin,
        "_json_get",
        lambda *_args, **_kwargs: {
            "qrcode": "qr-1",
            "qrcode_img_content": "data:image/png;base64,abc",
        },
    )

    payload, status = weixin.get_qrcode_payload()

    assert status == 200
    assert payload["qrcode"] == "qr-1"
    assert payload["qrcode_url"] == "data:image/png;base64,abc"
    assert payload["image"] == "data:image/png;base64,abc"


def test_weixin_qrcode_payload_encodes_login_url_as_image(monkeypatch):
    import api.weixin as weixin

    monkeypatch.setattr(
        weixin,
        "_json_get",
        lambda *_args, **_kwargs: {
            "qrcode": "qr-1",
            "qrcode_url": "https://liteapp.weixin.qq.com/q/redacted?qrcode=redacted&bot_type=3",
        },
    )

    payload, status = weixin.get_qrcode_payload()

    assert status == 200
    assert payload["qrcode"] == "qr-1"
    assert payload["qrcode_url"].startswith("https://liteapp.weixin.qq.com/q/")
    assert payload["image"].startswith("data:image/svg+xml;base64,")
    assert payload["image"] != payload["qrcode_url"]


def test_weixin_qrcode_status_route_returns_reference_shape(monkeypatch):
    import api.routes as routes
    import api.weixin as weixin

    _install_json_capture(monkeypatch)
    seen = []

    def fake_status(qrcode):
        seen.append(qrcode)
        return (
            {
                "status": "confirmed",
                "account_id": "acct-1",
                "token": "token-1",
                "base_url": "https://weixin.local",
            },
            200,
        )

    monkeypatch.setattr(weixin, "poll_qrcode_status_payload", fake_status)
    handler = _Handler()

    handled = routes.handle_get(handler, urlparse("/api/hermes/weixin/qrcode/status?qrcode=qr-1"))

    assert seen == ["qr-1"]
    assert handled["status"] == "confirmed"
    assert handled["account_id"] == "acct-1"
    assert handler.status == 200


def test_weixin_save_post_route_returns_success(monkeypatch):
    import api.routes as routes
    import api.weixin as weixin

    _install_json_capture(monkeypatch)
    seen = []

    def fake_save(body):
        seen.append(body)
        return ({"success": True}, 200)

    monkeypatch.setattr(weixin, "save_credentials_payload", fake_save)
    handler = _Handler({"account_id": "acct-1", "token": "token-1"})

    handled = routes.handle_post(handler, urlparse("/api/hermes/weixin/save"))

    assert seen == [{"account_id": "acct-1", "token": "token-1"}]
    assert handled == {"success": True}
    assert handler.status == 200


def test_weixin_qrcode_unavailable_returns_json_error_not_404(monkeypatch):
    import api.routes as routes
    import api.weixin as weixin

    _install_json_capture(monkeypatch)

    def unavailable():
        raise weixin.WeixinGatewayError(
            "Weixin iLink API is unavailable",
            status=503,
            code="weixin_upstream_unavailable",
        )

    monkeypatch.setattr(weixin, "get_qrcode_payload", unavailable)
    handler = _Handler()

    handled = routes.handle_get(handler, urlparse("/api/hermes/weixin/qrcode"))

    assert handler.status == 503
    assert handled["code"] == "weixin_upstream_unavailable"
    assert "error" in handled
