"""Safe channel configuration summaries for settings responses."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable


CHANNEL_SECRET_MARKER = "\u2022" * 8


def active_hermes_env_path(home: Path) -> Path:
    try:
        from api.profiles import get_active_hermes_home

        return Path(get_active_hermes_home()).expanduser() / ".env"
    except Exception:
        return Path(os.getenv("HERMES_HOME", str(home / ".hermes"))).expanduser() / ".env"


def channel_env_path_candidates(home: Path) -> list[Path]:
    candidates = [active_hermes_env_path(home)]
    if os.name == "nt":
        candidates.extend(
            [
                Path(r"\\wsl.localhost\Ubuntu-Hermes\home\xl\.hermes\.env"),
                Path(r"\\wsl$\Ubuntu-Hermes\home\xl\.hermes\.env"),
                Path(r"\\wsl.localhost\Ubuntu\home\xl\.hermes\.env"),
                Path(r"\\wsl$\Ubuntu\home\xl\.hermes\.env"),
            ]
        )
    return candidates


def read_env_entries(env_path: Path, keys: set[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        raw = env_path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return values
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in keys:
            values[key] = value.strip()
    return values


def get_safe_channel_platform_config_adapters(
    *,
    env_path_candidates: Callable[[], list[Path]],
    token_marker: str = CHANNEL_SECRET_MARKER,
) -> dict[str, dict]:
    env_values: dict[str, str] = {}
    keys = {"WEIXIN_ACCOUNT_ID", "WEIXIN_TOKEN", "WEIXIN_BASE_URL"}
    for env_path in env_path_candidates():
        env_values.update(
            {
                key: value
                for key, value in read_env_entries(env_path, keys).items()
                if key not in env_values and value
            }
        )
        if keys.issubset(env_values):
            break
    account_id = env_values.get("WEIXIN_ACCOUNT_ID", "")
    token = env_values.get("WEIXIN_TOKEN", "")
    base_url = env_values.get("WEIXIN_BASE_URL", "")
    if not any((account_id, token, base_url)):
        return {}
    weixin: dict[str, object] = {"source": "env"}
    if account_id:
        weixin["account_id"] = account_id
    if token:
        weixin["token_configured"] = True
        weixin["token"] = token_marker
    if base_url:
        weixin["base_url"] = base_url
    return {"weixin": weixin}
