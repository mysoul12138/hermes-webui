"""Weixin QR-login route registration kept outside ``api.routes``."""

from __future__ import annotations

from urllib.parse import parse_qs

from api.route_registry import RouteRegistry


def register_weixin_routes(registry: RouteRegistry) -> None:
    registry.get("/api/hermes/weixin/qrcode", _get_qrcode)
    registry.get("/api/hermes/weixin/qrcode/status", _get_qrcode_status)
    registry.post("/api/hermes/weixin/save", _save_credentials)


def _get_qrcode(handler, _parsed, ctx):
    from api.weixin import error_payload, get_qrcode_payload

    try:
        payload, status = get_qrcode_payload()
    except Exception as exc:
        payload, status = error_payload(exc)
    return ctx.j(handler, payload, status=status)


def _get_qrcode_status(handler, parsed, ctx):
    from api.weixin import error_payload, poll_qrcode_status_payload

    try:
        qrcode = parse_qs(parsed.query).get("qrcode", [""])[0]
        payload, status = poll_qrcode_status_payload(qrcode)
    except Exception as exc:
        payload, status = error_payload(exc)
    return ctx.j(handler, payload, status=status)


def _save_credentials(handler, _parsed, body: dict, ctx):
    from api.weixin import error_payload, save_credentials_payload

    try:
        payload, status = save_credentials_payload(body)
    except Exception as exc:
        payload, status = error_payload(exc)
    return ctx.j(handler, payload, status=status)

