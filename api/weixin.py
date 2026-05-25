"""Weixin QR-login adapter for the static WebUI channel panel.

This module mirrors the upstream Hermes BFF contract while keeping network and
credential-write details out of api.routes.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ILINK_BASE = "https://ilinkai.weixin.qq.com"
_QR_CAPACITY_L = {1: 19, 2: 34, 3: 55, 4: 80, 5: 108}
_QR_ECC_CODEWORDS_L = {1: 7, 2: 10, 3: 15, 4: 20, 5: 26}
_QR_ALIGNMENT_CENTERS = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30]}


class WeixinGatewayError(RuntimeError):
    def __init__(self, message: str, *, status: int = 502, code: str = "weixin_gateway_error"):
        super().__init__(message)
        self.status = status
        self.code = code


def _ilink_base_url() -> str:
    return os.getenv("HERMES_WEIXIN_ILINK_BASE", ILINK_BASE).strip().rstrip("/") or ILINK_BASE


def _json_get(path: str, params: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{_ilink_base_url()}{path}?{query}" if query else f"{_ilink_base_url()}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - fixed HTTPS API by default.
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise WeixinGatewayError(
            f"Weixin iLink API returned HTTP {exc.code}",
            status=502,
            code="weixin_upstream_http_error",
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WeixinGatewayError(
            f"Weixin iLink API is unavailable: {exc}",
            status=503,
            code="weixin_upstream_unavailable",
        ) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise WeixinGatewayError(
            "Weixin iLink API returned invalid JSON",
            status=502,
            code="weixin_upstream_invalid_json",
        ) from exc
    if not isinstance(payload, dict):
        raise WeixinGatewayError(
            "Weixin iLink API returned an unexpected payload",
            status=502,
            code="weixin_upstream_bad_shape",
        )
    return payload


def _gf_mul(x: int, y: int) -> int:
    z = 0
    while y:
        if y & 1:
            z ^= x
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
        y >>= 1
    return z & 0xFF


def _rs_generator(degree: int) -> list[int]:
    result = [1]
    root = 1
    for _ in range(degree):
        result = [_gf_mul(coef, root) for coef in result] + [0]
        for i in range(len(result) - 1):
            result[i + 1] ^= result[i]
        root = _gf_mul(root, 2)
    return result


def _rs_remainder(data: list[int], degree: int) -> list[int]:
    generator = _rs_generator(degree)
    result = [0] * degree
    for value in data:
        factor = value ^ result.pop(0)
        result.append(0)
        for i in range(degree):
            result[i] ^= _gf_mul(generator[i + 1], factor)
    return result


def _qr_add_bits(bits: list[int], value: int, count: int) -> None:
    for i in range(count - 1, -1, -1):
        bits.append((value >> i) & 1)


def _qr_data_codewords(payload: bytes, version: int) -> list[int]:
    capacity = _QR_CAPACITY_L[version]
    bits: list[int] = []
    _qr_add_bits(bits, 0b0100, 4)  # byte mode
    _qr_add_bits(bits, len(payload), 8)
    for byte in payload:
        _qr_add_bits(bits, byte, 8)
    remaining = capacity * 8 - len(bits)
    _qr_add_bits(bits, 0, min(4, remaining))
    while len(bits) % 8:
        bits.append(0)
    codewords = [sum(bit << (7 - i) for i, bit in enumerate(bits[j : j + 8])) for j in range(0, len(bits), 8)]
    pads = (0xEC, 0x11)
    while len(codewords) < capacity:
        codewords.append(pads[len(codewords) % 2])
    return codewords


def _qr_set(matrix: list[list[bool | None]], function: list[list[bool]], x: int, y: int, dark: bool) -> None:
    if 0 <= x < len(matrix) and 0 <= y < len(matrix):
        matrix[y][x] = dark
        function[y][x] = True


def _qr_draw_finder(matrix: list[list[bool | None]], function: list[list[bool]], x: int, y: int) -> None:
    for dy in range(-1, 8):
        for dx in range(-1, 8):
            xx, yy = x + dx, y + dy
            if 0 <= xx < len(matrix) and 0 <= yy < len(matrix):
                dark = 0 <= dx <= 6 and 0 <= dy <= 6 and (
                    dx in (0, 6) or dy in (0, 6) or (2 <= dx <= 4 and 2 <= dy <= 4)
                )
                _qr_set(matrix, function, xx, yy, dark)


def _qr_draw_alignment(matrix: list[list[bool | None]], function: list[list[bool]], cx: int, cy: int) -> None:
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            dark = max(abs(dx), abs(dy)) != 1
            _qr_set(matrix, function, cx + dx, cy + dy, dark)


def _qr_mask(mask: int, x: int, y: int) -> bool:
    if mask == 0:
        return (x + y) % 2 == 0
    if mask == 1:
        return y % 2 == 0
    if mask == 2:
        return x % 3 == 0
    if mask == 3:
        return (x + y) % 3 == 0
    if mask == 4:
        return (y // 2 + x // 3) % 2 == 0
    if mask == 5:
        return (x * y) % 2 + (x * y) % 3 == 0
    if mask == 6:
        return ((x * y) % 2 + (x * y) % 3) % 2 == 0
    return ((x + y) % 2 + (x * y) % 3) % 2 == 0


def _qr_penalty(matrix: list[list[bool]]) -> int:
    size = len(matrix)
    penalty = 0
    for y in range(size):
        run_color = matrix[y][0]
        run_len = 1
        for x in range(1, size):
            if matrix[y][x] == run_color:
                run_len += 1
            else:
                if run_len >= 5:
                    penalty += run_len - 2
                run_color = matrix[y][x]
                run_len = 1
        if run_len >= 5:
            penalty += run_len - 2
    for x in range(size):
        run_color = matrix[0][x]
        run_len = 1
        for y in range(1, size):
            if matrix[y][x] == run_color:
                run_len += 1
            else:
                if run_len >= 5:
                    penalty += run_len - 2
                run_color = matrix[y][x]
                run_len = 1
        if run_len >= 5:
            penalty += run_len - 2
    for y in range(size - 1):
        for x in range(size - 1):
            color = matrix[y][x]
            if matrix[y][x + 1] == color and matrix[y + 1][x] == color and matrix[y + 1][x + 1] == color:
                penalty += 3
    pattern = [True, False, True, True, True, False, True, False, False, False, False]
    inverse = [not value for value in pattern]
    for y in range(size):
        row = matrix[y]
        for x in range(size - 10):
            if row[x : x + 11] in (pattern, inverse):
                penalty += 40
    for x in range(size):
        col = [matrix[y][x] for y in range(size)]
        for y in range(size - 10):
            if col[y : y + 11] in (pattern, inverse):
                penalty += 40
    dark = sum(1 for row in matrix for value in row if value)
    penalty += abs(dark * 20 - size * size * 10) // (size * size) * 10
    return penalty


def _qr_format_bits(mask: int) -> int:
    data = (0b01 << 3) | mask  # Low error correction.
    rem = data << 10
    for i in range(14, 9, -1):
        if (rem >> i) & 1:
            rem ^= 0x537 << (i - 10)
    return ((data << 10) | (rem & 0x3FF)) ^ 0x5412


def _qr_draw_format(matrix: list[list[bool]], mask: int) -> None:
    size = len(matrix)
    bits = _qr_format_bits(mask)
    for i in range(6):
        matrix[8][i] = bool((bits >> i) & 1)
    matrix[8][7] = bool((bits >> 6) & 1)
    matrix[8][8] = bool((bits >> 7) & 1)
    matrix[7][8] = bool((bits >> 8) & 1)
    for i in range(9, 15):
        matrix[14 - i][8] = bool((bits >> i) & 1)
    for i in range(8):
        matrix[size - 1 - i][8] = bool((bits >> i) & 1)
    for i in range(8, 15):
        matrix[8][size - 15 + i] = bool((bits >> i) & 1)
    matrix[size - 8][8] = True


def _qr_matrix(text: str) -> list[list[bool]]:
    payload = text.encode("utf-8")
    version = next((v for v, capacity in _QR_CAPACITY_L.items() if len(payload) <= capacity - 2), 0)
    if not version:
        raise ValueError("QR payload is too long")
    size = version * 4 + 17
    matrix: list[list[bool | None]] = [[None] * size for _ in range(size)]
    function = [[False] * size for _ in range(size)]
    _qr_draw_finder(matrix, function, 0, 0)
    _qr_draw_finder(matrix, function, size - 7, 0)
    _qr_draw_finder(matrix, function, 0, size - 7)
    for i in range(8, size - 8):
        _qr_set(matrix, function, i, 6, i % 2 == 0)
        _qr_set(matrix, function, 6, i, i % 2 == 0)
    for cy in _QR_ALIGNMENT_CENTERS[version]:
        for cx in _QR_ALIGNMENT_CENTERS[version]:
            if function[cy][cx]:
                continue
            _qr_draw_alignment(matrix, function, cx, cy)
    for i in range(9):
        if i != 6:
            _qr_set(matrix, function, 8, i, False)
            _qr_set(matrix, function, i, 8, False)
    for i in range(8):
        _qr_set(matrix, function, size - 1 - i, 8, False)
        _qr_set(matrix, function, 8, size - 1 - i, False)
    _qr_set(matrix, function, 8, size - 8, True)

    data = _qr_data_codewords(payload, version)
    codewords = data + _rs_remainder(data, _QR_ECC_CODEWORDS_L[version])
    bit_index = 0
    direction = -1
    x = size - 1
    while x > 0:
        if x == 6:
            x -= 1
        for y in range(size - 1 if direction == -1 else 0, -1 if direction == -1 else size, direction):
            for dx in (0, 1):
                xx = x - dx
                if function[y][xx]:
                    continue
                value = bit_index < len(codewords) * 8 and bool((codewords[bit_index >> 3] >> (7 - (bit_index & 7))) & 1)
                matrix[y][xx] = value
                bit_index += 1
        direction = -direction
        x -= 2

    best_matrix: list[list[bool]] | None = None
    best_mask = 0
    best_penalty = 1 << 30
    for mask in range(8):
        candidate = [[bool(value) for value in row] for row in matrix]
        for y in range(size):
            for x in range(size):
                if not function[y][x] and _qr_mask(mask, x, y):
                    candidate[y][x] = not candidate[y][x]
        _qr_draw_format(candidate, mask)
        penalty = _qr_penalty(candidate)
        if penalty < best_penalty:
            best_matrix = candidate
            best_mask = mask
            best_penalty = penalty
    if best_matrix is None:
        raise ValueError("QR generation failed")
    _qr_draw_format(best_matrix, best_mask)
    return best_matrix


def _qr_svg_data_url(text: str) -> str:
    matrix = _qr_matrix(text)
    size = len(matrix)
    quiet = 4
    dark: list[str] = []
    for y, row in enumerate(matrix):
        for x, value in enumerate(row):
            if value:
                dark.append(f"M{x + quiet},{y + quiet}h1v1h-1z")
    viewbox = size + quiet * 2
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {viewbox} {viewbox}" shape-rendering="crispEdges">'
        '<path fill="#fff" d="M0 0h100%v100%H0z"/>'
        f'<path fill="#000" d="{"".join(dark)}"/></svg>'
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _looks_like_image_source(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.startswith("data:image/"):
        return True
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme in {"http", "https"}:
        return parsed.path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))
    return len(text) > 80 and all(ch.isalnum() or ch in "+/=\r\n" for ch in text)


def get_qrcode_payload() -> tuple[dict[str, Any], int]:
    data = _json_get("/ilink/bot/get_bot_qrcode", {"bot_type": 3}, timeout=15)
    qrcode = str(data.get("qrcode") or "").strip()
    qrcode_url = str(data.get("qrcode_url") or data.get("url") or data.get("qrcode_img_content") or "").strip()
    image = str(data.get("image") or data.get("qrcode_img_content") or "").strip()
    if not qrcode:
        raise WeixinGatewayError(
            "Weixin iLink API did not return a QR code",
            status=502,
            code="weixin_qrcode_missing",
        )
    payload = {"qrcode": qrcode, "qrcode_url": qrcode_url}
    if _looks_like_image_source(image):
        payload["image"] = image
    elif qrcode_url:
        payload["image"] = _qr_svg_data_url(qrcode_url)
    else:
        payload["image"] = _qr_svg_data_url(qrcode)
    return payload, 200


def poll_qrcode_status_payload(qrcode: str) -> tuple[dict[str, Any], int]:
    qrcode = str(qrcode or "").strip()
    if not qrcode:
        return {"error": "Missing qrcode parameter", "code": "missing_qrcode"}, 400
    data = _json_get("/ilink/bot/get_qrcode_status", {"qrcode": qrcode}, timeout=35)
    status = str(data.get("status") or "wait").strip() or "wait"
    if status == "confirmed":
        return {
            "status": "confirmed",
            "account_id": data.get("ilink_bot_id"),
            "token": data.get("bot_token"),
            "base_url": data.get("baseurl"),
        }, 200
    return {"status": status}, 200


def _active_env_path() -> Path:
    try:
        from api.profiles import get_active_hermes_home

        return Path(get_active_hermes_home()).expanduser() / ".env"
    except Exception:
        return Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser() / ".env"


def _write_env_entries(env_path: Path, entries: dict[str, str]) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    raw = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    seen: set[str] = set()
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in entries:
            lines.append(f"{key}={entries[key]}")
            seen.add(key)
        else:
            lines.append(line)
    for key, value in entries.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    content = "\n".join(lines).rstrip() + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(env_path.parent), delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, env_path)
    try:
        os.chmod(env_path, 0o600)
    except Exception:
        pass


def save_credentials_payload(body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    account_id = str(body.get("account_id") or "").strip()
    token = str(body.get("token") or "").strip()
    base_url = str(body.get("base_url") or "").strip()
    if not account_id or not token:
        return {"error": "Missing account_id or token", "code": "missing_weixin_credentials"}, 400
    entries = {
        "WEIXIN_ACCOUNT_ID": account_id,
        "WEIXIN_TOKEN": token,
    }
    if base_url:
        entries["WEIXIN_BASE_URL"] = base_url
    _write_env_entries(_active_env_path(), entries)
    return {"success": True, "restarted": False}, 200


def error_payload(exc: Exception) -> tuple[dict[str, Any], int]:
    if isinstance(exc, WeixinGatewayError):
        return {"error": str(exc), "code": exc.code}, exc.status
    return {"error": f"Weixin QR login failed: {exc}", "code": "weixin_unexpected_error"}, 502
