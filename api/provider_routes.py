"""Provider HTTP route helpers.

This module keeps provider-specific request handling out of ``api.routes``.
It deliberately accepts the response helpers from routes instead of importing
routes, which keeps the dependency direction one-way.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
import urllib.request
from urllib.parse import parse_qs, urlparse

from api.providers import (
    delete_custom_provider_config,
    get_providers,
    remove_provider_key,
    set_provider_key,
    upsert_custom_provider_config,
)

logger = logging.getLogger(__name__)


_OPENAI_COMPAT_ENDPOINTS = {
    "zai": "https://api.z.ai/v1",
    "minimax": "https://api.minimax.chat/v1",
    "mistralai": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}

_LIVE_MODELS_CACHE_TTL = 60.0
_LIVE_MODELS_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_LIVE_MODELS_CACHE_LOCK = threading.RLock()


def handle_get_providers(handler, j):
    return j(handler, get_providers())


def handle_post_providers(handler, body: dict, j, bad):
    if body.get("name") or body.get("base_url"):
        result = upsert_custom_provider_config(body)
        if not result.get("ok"):
            return bad(handler, result.get("error", "Unknown error"))
        return j(handler, result)
    provider_id = (body.get("provider") or "").strip().lower()
    api_key = body.get("api_key")
    if not provider_id:
        return bad(handler, "provider is required")
    if api_key is not None:
        api_key = str(api_key).strip() or None
    result = set_provider_key(provider_id, api_key)
    if not result.get("ok"):
        return bad(handler, result.get("error", "Unknown error"))
    return j(handler, result)


def handle_delete_provider(handler, body: dict, j, bad):
    provider_id = (body.get("provider") or "").strip().lower()
    if not provider_id:
        return bad(handler, "provider is required")
    if provider_id.startswith("custom:") or body.get("custom"):
        result = delete_custom_provider_config(provider_id)
    else:
        result = remove_provider_key(provider_id)
    if not result.get("ok"):
        return bad(handler, result.get("error", "Unknown error"))
    return j(handler, result)


def _active_profile_for_live_models_cache() -> str:
    try:
        from api.profiles import get_active_profile_name

        return get_active_profile_name() or "default"
    except Exception as exc:
        logger.debug("_active_profile_for_live_models_cache fell back to 'default': %s", exc)
        return "default"


def _live_models_cache_key(provider: str) -> tuple[str, str]:
    return (_active_profile_for_live_models_cache(), provider)


def _get_cached_live_models(key: tuple[str, str]) -> dict | None:
    now = time.monotonic()
    with _LIVE_MODELS_CACHE_LOCK:
        cached = _LIVE_MODELS_CACHE.get(key)
        if not cached:
            return None
        ts, payload = cached
        if now - ts >= _LIVE_MODELS_CACHE_TTL:
            _LIVE_MODELS_CACHE.pop(key, None)
            return None
        return copy.deepcopy(payload)


def _set_cached_live_models(key: tuple[str, str], payload: dict) -> None:
    with _LIVE_MODELS_CACHE_LOCK:
        _LIVE_MODELS_CACHE[key] = (time.monotonic(), copy.deepcopy(payload))


def _clear_live_models_cache() -> None:
    with _LIVE_MODELS_CACHE_LOCK:
        _LIVE_MODELS_CACHE.clear()


def _clear_live_models_cache_key(provider: str) -> None:
    with _LIVE_MODELS_CACHE_LOCK:
        _LIVE_MODELS_CACHE.pop(_live_models_cache_key(provider), None)


def _models_endpoint_from_base_url(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("base_url is required")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must start with http:// or https://")
    path = parsed.path.rstrip("/")
    if path.endswith("/v1/models") or path.endswith("/models"):
        return base
    return f"{base}/models" if path.endswith("/v1") else f"{base}/v1/models"


def _extract_model_ids_from_models_payload(payload, *, free_only: bool = False) -> list[str]:
    if isinstance(payload, dict):
        raw_models = payload.get("data", [])
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raw_models = []
    if not isinstance(raw_models, list):
        return []

    seen: set[str] = set()
    ids: list[str] = []
    for item in raw_models:
        model_id = ""
        if isinstance(item, dict):
            if free_only:
                pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
                is_free = (
                    str(item.get("id") or "").endswith(":free")
                    or item.get("free") is True
                    or item.get("is_free") is True
                    or (
                        str(pricing.get("prompt") or pricing.get("input") or "").strip() in {"", "0", "0.0"}
                        and str(pricing.get("completion") or pricing.get("output") or "").strip()
                        in {"", "0", "0.0"}
                    )
                )
                if not is_free:
                    continue
            model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
        elif not free_only:
            model_id = str(item or "").strip()
        if model_id and model_id not in seen:
            seen.add(model_id)
            ids.append(model_id)
    return sorted(ids, key=str.lower)


def _fetch_openai_compatible_model_ids(base_url: str, api_key: str = "", *, free_only: bool = False) -> list[str]:
    headers = {"Accept": "application/json", "User-Agent": "hermes-webui"}
    key = str(api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(_models_endpoint_from_base_url(base_url), headers=headers)
    with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310 - scheme validated above
        payload = json.loads(resp.read())
    return _extract_model_ids_from_models_payload(payload, free_only=free_only)


def _provider_connection_from_body(body: dict, *, allow_saved_key: bool = True) -> tuple[str, str, str]:
    provider = str(body.get("provider") or "").strip().lower()
    base_url = str(body.get("base_url") or "").strip()
    api_key = str(body.get("api_key") or "").strip()

    def _resolve_secret(raw, key_env=None) -> str:
        text = str(raw or "").strip()
        if text.startswith("${") and text.endswith("}") and len(text) > 3:
            text = os.getenv(text[2:-1], "").strip()
        if not text and key_env:
            text = os.getenv(str(key_env).strip(), "").strip()
        return text

    if provider and (not base_url or (allow_saved_key and not api_key)):
        try:
            from api.config import resolve_custom_provider_connection

            cfg_key, cfg_base = resolve_custom_provider_connection(provider)
            if not base_url and cfg_base:
                base_url = cfg_base
            if allow_saved_key and not api_key and cfg_key:
                api_key = cfg_key
        except Exception as exc:
            logger.debug("provider connection lookup failed for %s: %s", provider, exc)
    if provider and (not base_url or (allow_saved_key and not api_key)):
        try:
            from api.config import get_config as _gc

            providers_cfg = (_gc().get("providers", {}) or {})
            provider_cfg = providers_cfg.get(provider, {}) if isinstance(providers_cfg, dict) else {}
            if not isinstance(provider_cfg, dict) and provider.startswith("custom:"):
                provider_cfg = providers_cfg.get(provider.split(":", 1)[1], {})
            if isinstance(provider_cfg, dict):
                if not base_url:
                    base_url = str(provider_cfg.get("base_url") or "").strip()
                if allow_saved_key and not api_key:
                    api_key = _resolve_secret(provider_cfg.get("api_key"), provider_cfg.get("key_env"))
        except Exception as exc:
            logger.debug("provider config lookup failed for %s: %s", provider, exc)
    return provider, base_url, api_key


def handle_provider_models_fetch(handler, body: dict, j):
    provider, base_url, api_key = _provider_connection_from_body(body)
    endpoint = ""
    free_only = bool(body.get("freeOnly") or body.get("free_only"))
    try:
        endpoint = _models_endpoint_from_base_url(base_url)
        ids = _fetch_openai_compatible_model_ids(base_url, api_key, free_only=free_only)
    except Exception as exc:
        logger.debug("provider model fetch failed for %s %s: %s", provider or "custom", base_url, exc)
        detail = f" from {endpoint}" if endpoint else ""
        return j(
            handler,
            {
                "ok": False,
                "provider": provider or "custom",
                "models": [],
                "count": 0,
                "error": f"Failed to fetch models{detail}: {exc}",
            },
            status=502,
        )

    if not ids:
        return j(
            handler,
            {
                "ok": False,
                "provider": provider or "custom",
                "models": [],
                "count": 0,
                "message": f"No models were returned from {endpoint}. Check the base URL, API key, and whether the provider exposes /v1/models.",
            },
        )

    return j(
        handler,
        {
            "ok": True,
            "provider": provider or "custom",
            "models": [{"id": mid, "label": _make_live_model_label(provider or "custom", mid)} for mid in ids],
            "count": len(ids),
        },
    )


def _normalise_live_models_provider(provider: str) -> str:
    from api.config import _resolve_provider_alias, get_config

    provider = str(provider or "").strip().lower()
    if not provider:
        provider = (get_config().get("model", {}) or {}).get("provider") or ""
    return _resolve_provider_alias(provider) if provider else ""


def _make_live_model_label(provider: str, mid: str) -> str:
    from api.config import _format_ollama_label as _fmt_ollama

    if provider in ("ollama", "ollama-cloud"):
        return _fmt_ollama(mid)
    display = mid.split("/")[-1] if "/" in mid else mid
    parts = display.split("-")
    result = []
    for p in parts:
        pl = p.lower()
        if pl == "gpt":
            result.append("GPT")
        elif pl in ("claude", "gemini", "gemma", "llama", "mistral", "qwen", "deepseek", "grok", "kimi", "glm"):
            result.append(p.capitalize())
        elif p[:1].isdigit():
            result.append(p)
        else:
            result.append(p.capitalize())
    label = " ".join(result)
    for orig in ("GPT", "GLM", "API", "AI", "XL", "MoE"):
        label = label.replace(orig.title(), orig)
    return label


def handle_provider_models_refresh(handler, body: dict, j, bad):
    provider = _normalise_live_models_provider(body.get("provider"))
    if not provider:
        return bad(handler, "provider is required")
    _clear_live_models_cache_key(provider)

    if provider == "custom" or provider.startswith("custom:"):
        use_saved_key = bool(body.get("use_saved_key"))
        _, base_url, api_key = _provider_connection_from_body(
            {**body, "provider": provider},
            allow_saved_key=use_saved_key,
        )
        if not api_key:
            return bad(handler, "api_key is required to refresh custom provider models")
        endpoint = ""
        try:
            endpoint = _models_endpoint_from_base_url(base_url)
            ids = _fetch_openai_compatible_model_ids(base_url, api_key)
        except Exception as exc:
            detail = f" from {endpoint}" if endpoint else ""
            return j(
                handler,
                {
                    "ok": False,
                    "provider": provider,
                    "models": [],
                    "count": 0,
                    "error": f"Failed to refresh models{detail}: {exc}",
                },
                status=502,
            )
        models = [{"id": mid, "label": _make_live_model_label(provider, mid)} for mid in ids]
        payload = {"provider": provider, "models": models, "count": len(models)}
        if models:
            _set_cached_live_models(_live_models_cache_key(provider), payload)
    else:
        payload = live_models_payload_for_provider(provider)

    models = _normalize_models_payload(payload)
    payload["models"] = models
    payload["count"] = len(models)
    if payload.get("error"):
        payload["ok"] = False
        payload.setdefault("message", str(payload.get("error") or "Failed to refresh models"))
        return j(handler, payload, status=502)
    if not models:
        payload["ok"] = False
        payload.setdefault("message", f"No models were returned for {provider}. Check the base URL, API key, and whether the provider exposes /v1/models.")
        return j(handler, payload)
    payload["ok"] = True
    payload.setdefault("message", f"Models refreshed for {provider}")
    return j(handler, payload)


def _normalize_models_payload(payload: dict) -> list[dict]:
    models = payload.get("models") if isinstance(payload, dict) else []
    normalized = []
    seen = set()
    if not isinstance(models, list):
        return []
    for item in models:
        model_id = ""
        label = ""
        if isinstance(item, dict):
            model_id = str(item.get("id") or item.get("model") or item.get("name") or item.get("label") or "").strip()
            label = str(item.get("label") or model_id).strip()
        else:
            model_id = str(item or "").strip()
            label = model_id
        if model_id and model_id not in seen:
            seen.add(model_id)
            normalized.append({"id": model_id, "label": label or model_id})
    return normalized


def handle_live_models(handler, parsed, j):
    qs = parse_qs(parsed.query)
    provider = (qs.get("provider", [""])[0] or "").lower().strip()

    try:
        return j(handler, live_models_payload_for_provider(provider))
    except Exception as exc:
        logger.debug("_handle_live_models failed for %s: %s", provider, exc)
        return j(handler, {"error": str(exc), "models": []})


def live_models_payload_for_provider(provider: str) -> dict:
    from api.config import get_config

    cfg = get_config()
    if not provider:
        provider = cfg.get("model", {}).get("provider") or ""
    if not provider:
        return {"error": "no_provider", "models": []}

    from api.config import _resolve_provider_alias

    provider = _resolve_provider_alias(provider)

    cache_key = _live_models_cache_key(provider)
    cached = _get_cached_live_models(cache_key)
    if cached is not None:
        return cached

    def _finish(payload: dict):
        _set_cached_live_models(cache_key, payload)
        return payload

    try:
        try:
            import sys as _sys

            _agent_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "..",
                "..",
                ".hermes",
                "hermes-agent",
            )
            _agent_dir = os.path.normpath(_agent_dir)
            if _agent_dir not in _sys.path:
                _sys.path.insert(0, _agent_dir)
            from hermes_cli.models import provider_model_ids as _pmi

            ids = _pmi(provider)
        except Exception as import_err:
            logger.debug("provider_model_ids import failed for %s: %s", provider, import_err)
            ids = []

        if not ids:
            custom_provider_entry = None

            def _custom_provider_entries_for_request():
                if not (provider == "custom" or provider.startswith("custom:")):
                    return []
                try:
                    from api.config import _custom_provider_slug_from_name

                    cp_entries = cfg.get("custom_providers", [])
                    if not isinstance(cp_entries, list):
                        return []
                    matches = []
                    for cp in cp_entries:
                        if not isinstance(cp, dict):
                            continue
                        slug = _custom_provider_slug_from_name(cp.get("name", ""))
                        if provider.startswith("custom:"):
                            if slug == provider:
                                matches.append(cp)
                        elif provider == "custom" and not slug:
                            matches.append(cp)
                    return matches
                except Exception:
                    return []

            def _custom_provider_model_ids(cp):
                ids_out = []

                def _append(mid):
                    mid = str(mid or "").strip()
                    if mid and mid not in ids_out:
                        ids_out.append(mid)

                _append(cp.get("model", ""))
                models = cp.get("models")
                if isinstance(models, dict):
                    for mid in models:
                        if isinstance(mid, str):
                            _append(mid)
                elif isinstance(models, list):
                    for item in models:
                        if isinstance(item, str):
                            _append(item)
                        elif isinstance(item, dict):
                            _append(item.get("id") or item.get("model") or item.get("name"))
                return ids_out

            def _custom_provider_api_key(cp):
                raw = cp.get("api_key")
                if raw is not None:
                    key = str(raw).strip()
                    if key.startswith("${") and key.endswith("}") and len(key) > 3:
                        key = os.getenv(key[2:-1], "").strip()
                    if key:
                        return key
                env_name = str(cp.get("key_env") or "").strip()
                return os.getenv(env_name, "").strip() if env_name else ""

            if provider == "custom" or provider.startswith("custom:"):
                for cp in _custom_provider_entries_for_request():
                    if custom_provider_entry is None:
                        custom_provider_entry = cp
                    ids.extend(_custom_provider_model_ids(cp))

            if not ids and (provider == "custom" or provider.startswith("custom:")):
                base_url = None
                api_key = None
                if custom_provider_entry:
                    base_url = custom_provider_entry.get("base_url")
                    api_key = _custom_provider_api_key(custom_provider_entry)
                else:
                    model_cfg = cfg.get("model", {})
                    base_url = model_cfg.get("base_url")
                    api_key = model_cfg.get("api_key")
                if base_url and api_key:
                    try:
                        ids = _fetch_openai_compatible_model_ids(base_url, api_key)
                        if ids:
                            logger.debug("Live-fetched %d models from custom provider %s", len(ids), base_url)
                        else:
                            logger.debug("Custom provider returned no models from %s", base_url)
                    except Exception as fetch_err:
                        logger.debug("Live fetch from custom provider failed: %s", fetch_err)

        if not ids:
            ep = _OPENAI_COMPAT_ENDPOINTS.get(provider)
            if ep:
                try:
                    providers_cfg = cfg.get("providers", {})
                    prov = providers_cfg.get(provider, {}) if isinstance(providers_cfg, dict) else {}
                    key = prov.get("api_key") if isinstance(prov, dict) else None
                    if not key:
                        key = cfg.get("model", {}).get("api_key")
                    if key:
                        req = urllib.request.Request(
                            f"{ep}/models",
                            headers={"Authorization": f"Bearer {key}"},
                        )
                        with urllib.request.urlopen(req, timeout=8) as resp:
                            body = json.loads(resp.read())
                        ids = [m.get("id", "") for m in body.get("data", []) if m.get("id")]
                        logger.debug("Live-fetched %d models from %s /v1/models", len(ids), provider)
                except Exception as fetch_err:
                    logger.debug("Live fetch from %s failed: %s", provider, fetch_err)

        if not ids:
            from api.config import _PROVIDER_MODELS as provider_models

            ids = [m["id"] for m in provider_models.get(provider, [])]
        if not ids:
            return _finish({"provider": provider, "models": [], "count": 0})

        if provider == "nous":
            try:
                from api.config import _build_nous_featured_set

                default_model = (cfg.get("model", {}) or {}).get("model") if isinstance(cfg.get("model"), dict) else None
                featured, _ = _build_nous_featured_set(ids, selected_model_id=default_model)
                ids = featured
            except Exception:
                logger.debug("Failed to apply Nous featured-set cap for /api/models/live")

        models_out = [{"id": mid, "label": _make_live_model_label(provider, mid)} for mid in ids if mid]
        return _finish({"provider": provider, "models": models_out, "count": len(models_out)})

    except Exception as exc:
        logger.debug("_handle_live_models failed for %s: %s", provider, exc)
        return {"error": str(exc), "models": []}
