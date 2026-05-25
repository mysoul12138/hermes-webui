"""Provider route registration kept outside ``api.routes``."""

from __future__ import annotations

from api import provider_routes
from api.route_registry import RouteRegistry


def register_provider_routes(registry: RouteRegistry) -> None:
    registry.get("/api/providers", _get_providers)
    registry.get("/api/models/live", _get_live_models)
    registry.post("/api/providers", _post_providers)
    registry.post("/api/providers/delete", _delete_provider)
    registry.post("/api/models/refresh", _refresh_models)
    registry.post("/api/provider-models/fetch", _fetch_provider_models)


def _get_providers(handler, _parsed, ctx):
    return provider_routes.handle_get_providers(handler, ctx.j)


def _get_live_models(handler, parsed, ctx):
    return provider_routes.handle_live_models(handler, parsed, ctx.j)


def _post_providers(handler, _parsed, body: dict, ctx):
    return provider_routes.handle_post_providers(handler, body, ctx.j, ctx.bad)


def _delete_provider(handler, _parsed, body: dict, ctx):
    return provider_routes.handle_delete_provider(handler, body, ctx.j, ctx.bad)


def _refresh_models(handler, _parsed, body: dict, ctx):
    return provider_routes.handle_provider_models_refresh(handler, body, ctx.j, ctx.bad)


def _fetch_provider_models(handler, _parsed, body: dict, ctx):
    return provider_routes.handle_provider_models_fetch(handler, body, ctx.j)

