"""Small route dispatch registry for thin ``api.routes`` integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


RouteHandler = Callable[..., object]
NO_ROUTE = object()


@dataclass
class RouteRegistry:
    """Exact-path route registry used by the legacy BaseHTTPRequestHandler router."""

    get_routes: dict[str, RouteHandler] = field(default_factory=dict)
    post_routes: dict[str, RouteHandler] = field(default_factory=dict)

    def get(self, path: str, handler: RouteHandler) -> None:
        self.get_routes[path] = handler

    def post(self, path: str, handler: RouteHandler) -> None:
        self.post_routes[path] = handler

    def dispatch_get(self, request_handler, parsed, context) -> object:
        route = self.get_routes.get(parsed.path)
        if route is None:
            return NO_ROUTE
        return route(request_handler, parsed, context)

    def dispatch_post(self, request_handler, parsed, body: dict, context) -> object:
        route = self.post_routes.get(parsed.path)
        if route is None:
            return NO_ROUTE
        return route(request_handler, parsed, body, context)
